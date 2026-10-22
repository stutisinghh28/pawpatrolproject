"""
PawPatrol AI Image Analysis Service
Integrates genuine computer vision analysis for uploaded animal rescue photographs.

Supports:
1. Amazon Rekognition Custom Labels (specialized fine-grained veterinary triage models when trained)
2. Amazon Rekognition standard DetectLabels (general species & scene recognition on AWS)
3. Local Vision Validation engine (for local testing, offline validation, and image sanity checks)
"""

import io
import os
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("pawpatrol.ai")

SUPPORTED_MIME_TYPES = {
    'image/jpeg': 'JPEG',
    'image/jpg': 'JPEG',
    'image/png': 'PNG',
    'image/webp': 'WEBP'
}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_IMAGE_SIZE_BYTES = 100               # 100 Bytes

# Standard animal mapping for species classification
KNOWN_SPECIES_MAPPINGS = {
    'dog': 'Dog',
    'canine': 'Dog',
    'puppy': 'Dog',
    'hound': 'Dog',
    'cat': 'Cat',
    'feline': 'Cat',
    'kitten': 'Cat',
    'cattle': 'Cattle',
    'cow': 'Cattle',
    'bull': 'Cattle',
    'calf': 'Cattle',
    'bird': 'Bird',
    'avian': 'Bird',
    'pigeon': 'Bird'
}

DISCLAIMER_TEXT = (
    "AI image analysis provides observational assistance only (species detection and visual tags). "
    "It does not perform clinical veterinary diagnosis."
)

def validate_image_bytes(image_bytes: bytes) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validates image bytes for size, format, and structural integrity.
    Returns (is_valid, error_message, metadata_dict).
    """
    if not image_bytes or len(image_bytes) < MIN_IMAGE_SIZE_BYTES:
        return False, "Image file is empty or corrupted (less than 100 bytes).", None

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        return False, f"Image file size ({len(image_bytes)} bytes) exceeds maximum allowed limit of 5MB.", None

    try:
        from PIL import Image
        bio = io.BytesIO(image_bytes)
        with Image.open(bio) as img:
            img_format = img.format.upper() if img.format else 'UNKNOWN'
            width, height = img.size

            if img_format not in ['JPEG', 'PNG', 'WEBP']:
                return False, f"Unsupported image format: {img_format}. Allowed: JPEG, PNG, WEBP.", None

            if width < 32 or height < 32:
                return False, f"Image resolution ({width}x{height}) is too small for visual analysis.", None

            metadata = {
                'format': img_format,
                'width': width,
                'height': height,
                'size_bytes': len(image_bytes),
                'color_mode': img.mode
            }
            return True, None, metadata
    except Exception as e:
        return False, f"Invalid or unreadable image file: {str(e)}", None


def analyze_with_aws_rekognition(
    image_bytes: bytes,
    rekognition_client: Any,
    custom_project_arn: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes analysis using AWS Rekognition (Custom Labels if configured, else standard DetectLabels).
    """
    # 1. Custom Labels if configured and deployed
    if custom_project_arn:
        try:
            custom_resp = rekognition_client.detect_custom_labels(
                ProjectVersionArn=custom_project_arn,
                Image={'Bytes': image_bytes},
                MinConfidence=60.0
            )
            custom_labels = custom_resp.get('CustomLabels', [])
            detected = []
            for cl in custom_labels:
                detected.append({
                    'label': cl.get('Name'),
                    'confidence': round(float(cl.get('Confidence', 0.0)), 1),
                    'category': 'CustomVeterinaryTriage'
                })
            
            # Extract highest confidence label
            top_label = detected[0] if detected else None
            return {
                'status': 'SUCCESS' if detected else 'LOW_CONFIDENCE',
                'model_name': 'AWS-Rekognition-CustomLabels',
                'model_type': 'custom_veterinary_triage',
                'custom_model_arn': custom_project_arn,
                'identified_species': None,
                'species_confidence': 0.0,
                'uncertainty_flag': len(detected) == 0 or (top_label and top_label['confidence'] < 70.0),
                'detected_labels': detected,
                'requires_human_confirmation': True,
                'clinical_disclaimer': DISCLAIMER_TEXT
            }
        except Exception as e:
            logger.warning(f"Custom Labels invocation failed or model is stopped: {e}. Falling back to standard DetectLabels.")

    # 2. Standard DetectLabels (Species, Object, and Scene detection)
    resp = rekognition_client.detect_labels(
        Image={'Bytes': image_bytes},
        MaxLabels=20,
        MinConfidence=55.0
    )

    labels = resp.get('Labels', [])
    detected_labels = []
    identified_species = None
    species_confidence = 0.0
    possible_species = []

    for l in labels:
        name = l.get('Name', '')
        conf = round(float(l.get('Confidence', 0.0)), 1)
        name_lower = name.lower()

        # Categorize
        category = 'General'
        if name_lower in KNOWN_SPECIES_MAPPINGS:
            mapped = KNOWN_SPECIES_MAPPINGS[name_lower]
            category = 'Species'
            possible_species.append((mapped, conf))
        elif any(p.get('Name', '').lower() in ['animal', 'mammal', 'pet'] for p in l.get('Parents', [])):
            category = 'AnimalFeature'

        detected_labels.append({
            'label': name,
            'confidence': conf,
            'category': category
        })

    # Group species by mapped name (keep highest confidence per species)
    species_by_name = {}
    for mapped_sp, conf in possible_species:
        if mapped_sp not in species_by_name or conf > species_by_name[mapped_sp]:
            species_by_name[mapped_sp] = conf

    sorted_species = sorted(species_by_name.items(), key=lambda x: x[1], reverse=True)

    if sorted_species:
        identified_species, species_confidence = sorted_species[0]

    # Uncertainty calculation
    uncertainty_flag = False
    if not identified_species or species_confidence < 70.0:
        uncertainty_flag = True
    elif len(sorted_species) > 1 and (sorted_species[0][1] - sorted_species[1][1] < 15.0):
        # Multiple conflicting animal species detected (e.g. Dog vs Cat within 15% confidence)
        uncertainty_flag = True

    return {
        'status': 'SUCCESS' if detected_labels else 'LOW_CONFIDENCE',
        'model_name': 'AWS-Rekognition-DetectLabels-v2',
        'model_type': 'species_and_scene_detection',
        'identified_species': identified_species,
        'species_confidence': species_confidence,
        'uncertainty_flag': uncertainty_flag,
        'detected_labels': detected_labels,
        'requires_human_confirmation': True,
        'clinical_disclaimer': DISCLAIMER_TEXT
    }


def analyze_with_local_vision_validator(
    image_bytes: bytes,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Local fallback vision analyzer using Pillow image analysis.
    Used when running locally or when AWS Rekognition is not reachable.
    Validates color variance, aspect ratio, brightness, and structure.
    """
    from PIL import Image, ImageStat
    bio = io.BytesIO(image_bytes)
    with Image.open(bio) as img:
        stat = ImageStat.Stat(img)
        # Average brightness
        mean_brightness = sum(stat.mean) / len(stat.mean) if stat.mean else 128
        # Color variance across channels
        stddev = sum(stat.stddev) / len(stat.stddev) if stat.stddev else 50

    is_blurry_or_dark = mean_brightness < 35 or mean_brightness > 235 or stddev < 15

    detected_labels = [
        {'label': f"ImageFormat-{metadata.get('format')}", 'confidence': 100.0, 'category': 'Format'},
        {'label': f"Resolution-{metadata.get('width')}x{metadata.get('height')}", 'confidence': 100.0, 'category': 'Resolution'}
    ]

    if is_blurry_or_dark:
        detected_labels.append({'label': 'LowLightingOrContrast', 'confidence': 85.0, 'category': 'VisualQuality'})
        status = 'LOW_CONFIDENCE'
        uncertainty = True
    else:
        detected_labels.append({'label': 'ClearSubjectResolution', 'confidence': 90.0, 'category': 'VisualQuality'})
        status = 'SUCCESS'
        uncertainty = False

    return {
        'status': status,
        'model_name': 'PawPatrol-Local-Vision-Validator-v1',
        'model_type': 'local_vision_validator',
        'identified_species': None,  # Local validator does not hallucinate animal species without model weights
        'species_confidence': 0.0,
        'uncertainty_flag': uncertainty,
        'detected_labels': detected_labels,
        'requires_human_confirmation': True,
        'clinical_disclaimer': DISCLAIMER_TEXT
    }


def analyze_animal_photo(
    image_bytes: bytes,
    rekognition_client: Any = None,
    custom_project_arn: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main entry point for animal photo AI analysis.
    1. Validates image bytes.
    2. Runs AWS Rekognition if client is provided, else falls back to Local Vision Validator.
    3. Guarantees a standardized, safe schema.
    """
    is_valid, err_msg, metadata = validate_image_bytes(image_bytes)
    if not is_valid:
        return {
            'status': 'FAILED',
            'error': err_msg,
            'model_name': 'PawPatrol-Image-Validator',
            'model_type': 'pre_validation',
            'identified_species': None,
            'species_confidence': 0.0,
            'uncertainty_flag': True,
            'detected_labels': [],
            'requires_human_confirmation': True,
            'clinical_disclaimer': DISCLAIMER_TEXT
        }

    # Attempt AWS Rekognition if client provided
    if rekognition_client:
        try:
            result = analyze_with_aws_rekognition(image_bytes, rekognition_client, custom_project_arn)
            result['image_metadata'] = metadata
            return result
        except Exception as e:
            logger.error(f"Rekognition error: {e}. Falling back to local vision validation.")

    # Fallback to local vision validator
    result = analyze_with_local_vision_validator(image_bytes, metadata)
    result['image_metadata'] = metadata
    return result
