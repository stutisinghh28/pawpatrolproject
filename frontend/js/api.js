/**
 * PawPatrol API Service
 * Handles unified communication with:
 *  1. AWS Lambda HTTPS Endpoint (Function URL / API Gateway)
 *  2. Local Python Development Server (http://localhost:8000)
 *  3. Explicit Offline LocalStorage Mode (clearly labeled, never silently masked)
 */

const API = {
  baseUrl: localStorage.getItem('pawpatrol_api_url') || '',
  explicitOfflineMode: localStorage.getItem('pawpatrol_offline_mode') === 'true',

  setBaseUrl(url) {
    this.baseUrl = url.trim().replace(/\/+$/, '');
    localStorage.setItem('pawpatrol_api_url', this.baseUrl);
    if (this.baseUrl) {
      this.setOfflineMode(false);
    }
  },

  getBaseUrl() {
    return this.baseUrl;
  },

  setOfflineMode(enabled) {
    this.explicitOfflineMode = Boolean(enabled);
    localStorage.setItem('pawpatrol_offline_mode', this.explicitOfflineMode ? 'true' : 'false');
  },

  isOfflineMode() {
    return this.explicitOfflineMode;
  },

  getStorageMode() {
    if (this.explicitOfflineMode) return 'OFFLINE_LOCAL';
    if (this.baseUrl.includes('amazonaws.com')) return 'AWS_CLOUD';
    return 'LOCAL_SERVER';
  },

  // Check health / connectivity
  async ping() {
    if (this.explicitOfflineMode) return false;
    try {
      const url = this.baseUrl ? `${this.baseUrl}/reports` : '/api/reports';
      const res = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
      return res.ok;
    } catch (e) {
      return false;
    }
  },

  // AI Photo Analysis Endpoint
  async analyzePhoto(imageBase64) {
    if (this.explicitOfflineMode) {
      // Local client-side simulation when completely offline
      return {
        status: 'SUCCESS',
        model_name: 'PawPatrol-Client-Vision-Simulator',
        model_type: 'client_offline_simulation',
        identified_species: null,
        species_confidence: 0.0,
        uncertainty_flag: true,
        detected_labels: [
          { label: 'OfflineImageProvided', confidence: 100.0, category: 'Offline' }
        ],
        clinical_disclaimer: 'Offline mode active: AI analysis requires server connectivity.'
      };
    }

    const url = this.baseUrl ? `${this.baseUrl}/analyze-photo` : '/api/analyze-photo';
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_base64: imageBase64 })
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`AI Analysis failed (${res.status}): ${err}`);
    }

    const data = await res.json();
    return data.analysis || data;
  },

  // Request S3 Pre-signed URL or Local Upload Endpoint
  async getUploadUrl(filename, contentType) {
    const url = this.baseUrl ? `${this.baseUrl}/upload-url` : '/api/upload-url';
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, content_type: contentType })
    });

    if (!res.ok) {
      throw new Error(`Could not obtain upload URL (${res.status})`);
    }
    return await res.json();
  },

  // Upload Photo File (S3 Presigned PUT or Local Server)
  async uploadPhoto(file, imageBase64) {
    if (this.explicitOfflineMode) {
      // Store nothing large, keep a reference
      return {
        photo_url: imageBase64,
        photo_s3_key: null,
        storage_tier: 'LOCAL_OFFLINE_CACHE'
      };
    }

    // 1. AWS Cloud route with S3 Presigned URL
    if (this.baseUrl && this.baseUrl.includes('amazonaws.com')) {
      const presigned = await this.getUploadUrl(file.name, file.type);
      if (!presigned || !presigned.upload_url) {
        throw new Error('S3 presigned upload URL was not returned by server');
      }

      // Direct PUT to private S3 bucket
      const putRes = await fetch(presigned.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type },
        body: file
      });

      if (!putRes.ok) {
        throw new Error(`Direct S3 image upload failed with HTTP ${putRes.status}`);
      }

      return {
        photo_s3_key: presigned.key,
        photo_url: null, // S3 key is stored; backend generates presigned download URL
        storage_tier: 'AWS_S3'
      };
    }

    // 2. Local Python Server upload route
    try {
      const localRes = await fetch('/api/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: file.name,
          image_base64: imageBase64
        })
      });

      if (localRes.ok) {
        const localData = await localRes.json();
        return {
          photo_url: localData.photo_url,
          photo_s3_key: localData.photo_s3_key,
          storage_tier: 'LOCAL_SERVER_DISK'
        };
      }
    } catch (e) {
      console.warn('Local file upload endpoint unreachable:', e);
    }

    throw new Error('Unable to upload photo to server. Check your connection or enable Offline Mode.');
  },

  // Submit a new rescue report (NO SILENT FALLBACK!)
  async createReport(reportData) {
    if (this.explicitOfflineMode) {
      return this._saveOfflineDraft(reportData);
    }

    const url = this.baseUrl ? `${this.baseUrl}/reports` : '/api/reports';
    let res;
    try {
      res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reportData)
      });
    } catch (networkErr) {
      throw new Error(`Cannot connect to server at ${url}. Check if the server is running or switch to Offline Mode in Settings.`);
    }

    if (!res.ok) {
      const errText = await res.text();
      let parsedErr = errText;
      try {
        const jsonErr = JSON.parse(errText);
        parsedErr = jsonErr.error || jsonErr.message || errText;
      } catch (_) {}
      throw new Error(`Server rejected report (${res.status}): ${parsedErr}`);
    }

    return await res.json();
  },

  // Fetch reports with optional filters
  async getReports(filters = {}) {
    if (this.explicitOfflineMode) {
      return this._getOfflineDrafts(filters);
    }

    const params = new URLSearchParams();
    if (filters.risk_level && filters.risk_level !== 'ALL') params.append('risk_level', filters.risk_level);
    if (filters.status && filters.status !== 'ALL') params.append('status', filters.status);
    if (filters.animal_type && filters.animal_type !== 'ALL') params.append('animal_type', filters.animal_type);

    const queryString = params.toString() ? `?${params.toString()}` : '';
    const url = this.baseUrl ? `${this.baseUrl}/reports${queryString}` : `/api/reports${queryString}`;

    let res;
    try {
      res = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
    } catch (networkErr) {
      throw new Error(`Cannot connect to server at ${url}. Check server status.`);
    }

    if (!res.ok) {
      throw new Error(`Failed to fetch reports (${res.status})`);
    }

    return await res.json();
  },

  // Update report status
  async updateReportStatus(reportId, updates) {
    if (this.explicitOfflineMode) {
      return this._updateOfflineDraft(reportId, updates);
    }

    const url = this.baseUrl ? `${this.baseUrl}/reports/${reportId}` : `/api/reports/${reportId}`;
    let res;
    try {
      res = await fetch(url, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });
    } catch (networkErr) {
      throw new Error(`Cannot connect to server to update status.`);
    }

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Status update failed (${res.status}): ${errText}`);
    }

    return await res.json();
  },

  // ------------------------------------------------------------------------
  // Explicit Offline Drafts Storage
  // ------------------------------------------------------------------------
  _getStoredDrafts() {
    try {
      return JSON.parse(localStorage.getItem('pawpatrol_local_drafts') || '[]');
    } catch (e) {
      return [];
    }
  },

  _saveStoredDrafts(drafts) {
    localStorage.setItem('pawpatrol_local_drafts', JSON.stringify(drafts));
  },

  _saveOfflineDraft(reportData) {
    const drafts = this._getStoredDrafts();
    const newReport = {
      ...reportData,
      report_id: `LOCAL-DRAFT-${Date.now().toString(36).toUpperCase()}`,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      status: 'REPORTED',
      storage_tier: 'LOCAL_OFFLINE_CACHE',
      offline: true
    };
    drafts.unshift(newReport);
    this._saveStoredDrafts(drafts);
    return { success: true, report: newReport, offline: true, storage_tier: 'LOCAL_OFFLINE_CACHE' };
  },

  _getOfflineDrafts(filters) {
    let drafts = this._getStoredDrafts();
    if (filters.risk_level && filters.risk_level !== 'ALL') {
      drafts = drafts.filter(r => r.risk_level === filters.risk_level);
    }
    if (filters.status && filters.status !== 'ALL') {
      drafts = drafts.filter(r => r.status === filters.status);
    }
    if (filters.animal_type && filters.animal_type !== 'ALL') {
      drafts = drafts.filter(r => r.animal_type === filters.animal_type);
    }
    return { success: true, reports: drafts, count: drafts.length, offline: true, storage_tier: 'LOCAL_OFFLINE_CACHE' };
  },

  _updateOfflineDraft(reportId, updates) {
    const drafts = this._getStoredDrafts();
    const idx = drafts.findIndex(r => r.report_id === reportId);
    if (idx !== -1) {
      drafts[idx] = { ...drafts[idx], ...updates, updated_at: new Date().toISOString() };
      this._saveStoredDrafts(drafts);
      return { success: true, report: drafts[idx], offline: true };
    }
    throw new Error('Report not found in local offline storage');
  }
};

window.API = API;
