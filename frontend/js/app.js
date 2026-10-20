/**
 * PawPatrol - Main Application Logic
 * Implements rule-based risk classification, form handling, dashboard UI, and API integration.
 */

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

const App = {
  currentTab: 'report',
  cachedReports: [],
  selectedPhotoFile: null,
  selectedPhotoBase64: null,

  init() {
    this.bindNavigation();
    this.bindFormEvents();
    this.bindDashboardFilters();
    this.bindSettingsModal();
    this.checkApiStatus();

    // Initialize Map on Report form
    MapModule.initPicker('picker-map', (lat, lng) => {
      document.getElementById('input-lat').value = lat.toFixed(6);
      document.getElementById('input-lng').value = lng.toFixed(6);
    });

    // Initial Risk Assessment Calculation
    this.calculateRiskLevel();
  },

  // ------------------------------------------------------------------------
  // Navigation & Tabs
  // ------------------------------------------------------------------------
  bindNavigation() {
    const navButtons = document.querySelectorAll('.nav-tab-btn');
    navButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        this.switchTab(targetTab);
      });
    });
  },

  switchTab(tabName) {
    this.currentTab = tabName;
    document.querySelectorAll('.nav-tab-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-tab') === tabName);
    });
    document.querySelectorAll('.tab-pane').forEach(p => {
      p.classList.toggle('active', p.id === `tab-${tabName}`);
    });

    if (tabName === 'dashboard') {
      this.loadDashboardData();
    } else if (tabName === 'map') {
      setTimeout(() => {
        MapModule.initDashboardMap('dashboard-full-map');
        MapModule.plotReports(this.cachedReports);
      }, 100);
    }
  },

  // ------------------------------------------------------------------------
  // Rule-Based Risk Classification Logic
  // ------------------------------------------------------------------------
  calculateRiskLevel() {
    const condition = document.getElementById('select-condition').value;
    const checkedSymptoms = Array.from(document.querySelectorAll('input[name="symptoms"]:checked')).map(el => el.value);
    const animalAge = document.querySelector('input[name="animal_age"]:checked')?.value || 'adult';
    const isTrapped = document.getElementById('check-trapped')?.checked || false;

    let score = 0;
    let riskLevel = 'LOW';
    let reasons = [];

    // 1. Primary Condition Weight
    if (condition === 'CRITICAL_INJURY') {
      score += 8;
      reasons.push('Severe/Life-threatening condition selected');
    } else if (condition === 'MODERATE_INJURY') {
      score += 4;
      reasons.push('Moderate injury or acute illness');
    } else if (condition === 'SKIN_OR_SICK') {
      score += 2;
      reasons.push('Chronic condition / mange / malnutrition');
    } else if (condition === 'HEALTHY_STRAY') {
      score += 1;
      reasons.push('General stray / routine care');
    }

    // 2. Specific Symptoms Weight
    if (checkedSymptoms.includes('unconscious')) {
      score += 10;
      reasons.push('Animal is unresponsive / unconscious');
    }
    if (checkedSymptoms.includes('bleeding_heavily')) {
      score += 6;
      reasons.push('Active heavy bleeding reported');
    }
    if (checkedSymptoms.includes('hit_by_vehicle')) {
      score += 5;
      reasons.push('Hit-and-run / vehicular trauma');
    }
    if (checkedSymptoms.includes('broken_bone')) {
      score += 4;
      reasons.push('Suspected bone fracture / immobility');
    }
    if (checkedSymptoms.includes('rabies_symptoms')) {
      score += 6;
      reasons.push('Suspected neurological / rabies distress');
    }
    if (checkedSymptoms.includes('skin_mange')) {
      score += 2;
      reasons.push('Severe skin disease or loss of fur');
    }
    if (checkedSymptoms.includes('severe_malnutrition')) {
      score += 3;
      reasons.push('Extreme emaciation / dehydration');
    }

    // 3. Environmental / Vulnerability Multipliers
    if (isTrapped) {
      score += 4;
      reasons.push('Trapped in dangerous hazard');
    }
    if (animalAge === 'infant') {
      score += 2;
      reasons.push('Vulnerable newborn / infant animal');
    }

    // Classification Rules:
    if (score >= 12 || checkedSymptoms.includes('unconscious') || (checkedSymptoms.includes('bleeding_heavily') && (checkedSymptoms.includes('hit_by_vehicle') || condition === 'CRITICAL_INJURY'))) {
      riskLevel = 'CRITICAL';
    } else if (score >= 7 || checkedSymptoms.includes('broken_bone') || checkedSymptoms.includes('hit_by_vehicle')) {
      riskLevel = 'HIGH';
    } else if (score >= 4 || checkedSymptoms.includes('skin_mange') || isTrapped) {
      riskLevel = 'MEDIUM';
    } else {
      riskLevel = 'LOW';
    }

    this.renderRiskPreview(riskLevel, score, reasons);
    return { riskLevel, score, reasons };
  },

  renderRiskPreview(level, score, reasons) {
    const box = document.getElementById('risk-preview-box');
    const badge = document.getElementById('risk-badge');
    const desc = document.getElementById('risk-explanation');
    const sla = document.getElementById('risk-sla');

    if (!box || !badge) return;

    box.className = `risk-preview-box risk-${level.toLowerCase()}`;
    badge.className = `risk-level-badge ${level.toLowerCase()}`;
    badge.textContent = `${level} PRIORITY (Score: ${score})`;

    const slaMap = {
      'CRITICAL': 'Target Dispatch: Immediate (< 30 mins) | Automated Emergency Alerts Triggered',
      'HIGH': 'Target Dispatch: Priority (< 2 hours) | Volunteer Notification Queued',
      'MEDIUM': 'Target Dispatch: Standard (< 12 hours) | Routine Volunteer Assessment',
      'LOW': 'Target Dispatch: Routine / Non-Emergency (< 48 hours) | Scheduled Care'
    };

    sla.textContent = slaMap[level];
    desc.innerHTML = `<strong>Assessment Rationale:</strong> ${reasons.length > 0 ? reasons.join(' • ') : 'Standard evaluation'}.`;
  },

  // ------------------------------------------------------------------------
  // Form Events & Submission
  // ------------------------------------------------------------------------
  bindFormEvents() {
    // Re-evaluate risk on condition or symptom change
    document.getElementById('select-condition').addEventListener('change', () => this.calculateRiskLevel());
    document.querySelectorAll('input[name="symptoms"]').forEach(cb => {
      cb.addEventListener('change', () => this.calculateRiskLevel());
    });
    document.querySelectorAll('input[name="animal_age"]').forEach(r => {
      r.addEventListener('change', () => this.calculateRiskLevel());
    });
    const trappedBox = document.getElementById('check-trapped');
    if (trappedBox) trappedBox.addEventListener('change', () => this.calculateRiskLevel());

    // GPS Button
    const gpsBtn = document.getElementById('btn-get-gps');
    if (gpsBtn) {
      gpsBtn.addEventListener('click', () => {
        gpsBtn.innerHTML = '<span class="spinner"></span> Locating...';
        gpsBtn.disabled = true;

        MapModule.getUserLocation(
          (lat, lng) => {
            document.getElementById('input-lat').value = lat.toFixed(6);
            document.getElementById('input-lng').value = lng.toFixed(6);
            MapModule.setPickerLocation(lat, lng);
            gpsBtn.innerHTML = '📍 Location Captured!';
            setTimeout(() => {
              gpsBtn.innerHTML = '📍 Use My Current Location';
              gpsBtn.disabled = false;
            }, 2500);
            this.showToast('Location captured successfully', 'success');
          },
          (err) => {
            gpsBtn.innerHTML = '📍 Use My Current Location';
            gpsBtn.disabled = false;
            this.showToast(`GPS error: ${err}`, 'error');
          }
        );
      });
    }

    // Photo Upload & Preview
    const photoInput = document.getElementById('input-photo');
    const dropzone = document.getElementById('photo-dropzone');
    const previewContainer = document.getElementById('photo-preview-container');
    const previewImg = document.getElementById('photo-preview-img');
    const removeBtn = document.getElementById('btn-remove-photo');

    if (dropzone && photoInput) {
      dropzone.addEventListener('click', () => photoInput.click());

      photoInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;

        if (file.size > 5 * 1024 * 1024) {
          this.showToast('Photo must be less than 5MB', 'error');
          return;
        }

        this.selectedPhotoFile = file;
        const reader = new FileReader();
        reader.onload = (ev) => {
          this.selectedPhotoBase64 = ev.target.result;
          previewImg.src = ev.target.result;
          previewContainer.style.display = 'block';
          dropzone.style.display = 'none';
        };
        reader.readAsDataURL(file);
      });

      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.selectedPhotoFile = null;
        this.selectedPhotoBase64 = null;
        photoInput.value = '';
        previewContainer.style.display = 'none';
        dropzone.style.display = 'block';
      });
    }

    // Form Submit
    const form = document.getElementById('report-form');
    if (form) {
      form.addEventListener('submit', (e) => this.handleFormSubmit(e));
    }
  },

  async handleFormSubmit(e) {
    e.preventDefault();

    const submitBtn = document.getElementById('btn-submit-report');
    const originalBtnText = submitBtn.innerHTML;

    // Form inputs
    const animalType = document.getElementById('select-animal-type').value;
    const condition = document.getElementById('select-condition').value;
    const address = document.getElementById('input-address').value.trim();
    const lat = document.getElementById('input-lat').value.trim();
    const lng = document.getElementById('input-lng').value.trim();
    const description = document.getElementById('input-description').value.trim();
    const reporterName = document.getElementById('input-reporter-name').value.trim();
    const reporterPhone = document.getElementById('input-reporter-phone').value.trim();
    const animalAge = document.querySelector('input[name="animal_age"]:checked')?.value || 'adult';
    const isTrapped = document.getElementById('check-trapped')?.checked || false;

    const checkedSymptoms = Array.from(document.querySelectorAll('input[name="symptoms"]:checked')).map(el => el.value);

    // Validation
    if (!animalType) {
      this.showToast('Please select the animal type', 'error');
      return;
    }
    if (!address) {
      this.showToast('Please provide a landmark or location address', 'error');
      document.getElementById('input-address').focus();
      return;
    }
    if (!description) {
      this.showToast('Please provide a brief description of the situation', 'error');
      document.getElementById('input-description').focus();
      return;
    }

    // Calculate risk
    const assessment = this.calculateRiskLevel();

    // Prepare Payload
    const reportPayload = {
      animal_type: animalType,
      animal_age: animalAge,
      condition: condition,
      symptoms: checkedSymptoms,
      is_trapped: isTrapped,
      description: description,
      location_address: address,
      latitude: lat ? parseFloat(lat) : null,
      longitude: lng ? parseFloat(lng) : null,
      reporter_name: reporterName || 'Anonymous Citizen',
      reporter_phone: reporterPhone || '',
      risk_level: assessment.riskLevel,
      risk_score: assessment.score,
      risk_reasons: assessment.reasons,
      photo_data: this.selectedPhotoBase64 || null,
      photo_url: null,
      status: 'REPORTED'
    };

    try {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner"></span> Dispatching Report...';

      // If photo was chosen and we have AWS S3 Pre-signed URL capability
      if (this.selectedPhotoFile && API.getBaseUrl()) {
        try {
          const presigned = await API.getUploadUrl(this.selectedPhotoFile.name, this.selectedPhotoFile.type);
          if (presigned && presigned.upload_url) {
            await fetch(presigned.upload_url, {
              method: 'PUT',
              headers: { 'Content-Type': this.selectedPhotoFile.type },
              body: this.selectedPhotoFile
            });
            reportPayload.photo_url = presigned.photo_url;
            reportPayload.photo_data = null; // Do not need inline base64 if hosted on S3
          }
        } catch (s3Err) {
          console.warn('S3 upload fallback to base64 payload:', s3Err);
        }
      }

      const result = await API.createReport(reportPayload);

      if (result && (result.success || result.report_id || result.report)) {
        const createdReport = result.report || result;
        this.showSuccessModal(createdReport);
        this.resetForm();
        this.showToast('Rescue report submitted successfully!', 'success');
      } else {
        throw new Error(result.error || 'Failed to submit report');
      }
    } catch (err) {
      this.showToast(`Submission failed: ${err.message}`, 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalBtnText;
    }
  },

  resetForm() {
    document.getElementById('report-form').reset();
    this.selectedPhotoFile = null;
    this.selectedPhotoBase64 = null;
    const previewContainer = document.getElementById('photo-preview-container');
    const dropzone = document.getElementById('photo-dropzone');
    if (previewContainer) previewContainer.style.display = 'none';
    if (dropzone) dropzone.style.display = 'block';
    this.calculateRiskLevel();
  },

  showSuccessModal(report) {
    const modal = document.getElementById('modal-success');
    const idEl = document.getElementById('modal-success-id');
    const riskEl = document.getElementById('modal-success-risk');
    const descEl = document.getElementById('modal-success-desc');

    const reportId = report.report_id || 'PAW-TRACKED';
    idEl.textContent = reportId;
    riskEl.textContent = `${report.risk_level} Priority`;
    riskEl.className = `badge badge-${report.risk_level.toLowerCase()}`;
    descEl.textContent = `Report for ${report.animal_type} at ${report.location_address} has been logged and dispatched.`;

    modal.classList.add('open');
  },

  // ------------------------------------------------------------------------
  // Dashboard & KPI Filtering
  // ------------------------------------------------------------------------
  bindDashboardFilters() {
    const searchInput = document.getElementById('filter-search');
    const riskFilter = document.getElementById('filter-risk');
    const statusFilter = document.getElementById('filter-status');
    const animalFilter = document.getElementById('filter-animal');
    const refreshBtn = document.getElementById('btn-refresh-dashboard');

    const handleFilterChange = () => this.applyDashboardFilters();

    if (searchInput) searchInput.addEventListener('input', handleFilterChange);
    if (riskFilter) riskFilter.addEventListener('change', handleFilterChange);
    if (statusFilter) statusFilter.addEventListener('change', handleFilterChange);
    if (animalFilter) animalFilter.addEventListener('change', handleFilterChange);
    if (refreshBtn) refreshBtn.addEventListener('click', () => this.loadDashboardData());
  },

  async loadDashboardData() {
    const container = document.getElementById('reports-container');
    if (!container) return;

    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 3rem;"><span class="spinner" style="border-color: #2563eb; border-top-color: transparent; width: 32px; height: 32px;"></span><p style="margin-top: 1rem; color: #64748b;">Loading rescue reports...</p></div>';

    try {
      const res = await API.getReports();
      const reports = res.reports || [];
      this.cachedReports = reports;

      this.updateKpiCounters(reports);
      this.applyDashboardFilters();
    } catch (err) {
      container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #ef4444;">Failed to load reports: ${err.message}</div>`;
    }
  },

  updateKpiCounters(reports) {
    const totalEl = document.getElementById('kpi-total-val');
    const criticalEl = document.getElementById('kpi-critical-val');
    const progressEl = document.getElementById('kpi-progress-val');
    const rescuedEl = document.getElementById('kpi-rescued-val');

    const total = reports.length;
    const critical = reports.filter(r => r.risk_level === 'CRITICAL' || r.risk_level === 'HIGH').length;
    const progress = reports.filter(r => r.status === 'IN_PROGRESS' || r.status === 'DISPATCHED' || r.status === 'IN_TREATMENT').length;
    const rescued = reports.filter(r => r.status === 'RESCUED' || r.status === 'CLOSED').length;

    if (totalEl) totalEl.textContent = total;
    if (criticalEl) criticalEl.textContent = critical;
    if (progressEl) progressEl.textContent = progress;
    if (rescuedEl) rescuedEl.textContent = rescued;
  },

  applyDashboardFilters() {
    const searchText = (document.getElementById('filter-search')?.value || '').toLowerCase().trim();
    const riskVal = document.getElementById('filter-risk')?.value || 'ALL';
    const statusVal = document.getElementById('filter-status')?.value || 'ALL';
    const animalVal = document.getElementById('filter-animal')?.value || 'ALL';

    let filtered = this.cachedReports.filter(rep => {
      if (riskVal !== 'ALL' && rep.risk_level !== riskVal) return false;
      if (statusVal !== 'ALL' && rep.status !== statusVal) return false;
      if (animalVal !== 'ALL' && rep.animal_type !== animalVal) return false;

      if (searchText) {
        const hay = `${rep.report_id || ''} ${rep.animal_type || ''} ${rep.location_address || ''} ${rep.description || ''} ${rep.reporter_name || ''}`.toLowerCase();
        if (!hay.includes(searchText)) return false;
      }
      return true;
    });

    this.renderReportsList(filtered);
  },

  renderReportsList(reports) {
    const container = document.getElementById('reports-container');
    if (!container) return;

    if (reports.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; padding: 4rem 1rem; background: #ffffff; border: 1px dashed #cbd5e1; border-radius: 12px;">
          <div style="font-size: 3rem; margin-bottom: 0.5rem;">🐾</div>
          <h3 style="color: #1e293b; font-size: 1.1rem; font-weight: 700;">No rescue reports found</h3>
          <p style="color: #64748b; font-size: 0.85rem; margin-top: 0.25rem;">Try adjusting your filters or submit a new rescue report.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = reports.map(rep => {
      const riskClass = `badge-${(rep.risk_level || 'LOW').toLowerCase()}`;
      const photoSrc = rep.photo_url || rep.photo_data;
      const relativeTime = this.formatRelativeTime(rep.created_at);

      return `
        <div class="report-card">
          <div class="report-card-top">
            ${photoSrc 
              ? `<img src="${photoSrc}" alt="${rep.animal_type}" class="report-card-img" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                 <div class="report-card-placeholder" style="display:none;">🐾</div>`
              : `<div class="report-card-placeholder">🐾</div>`}
            <div class="report-badge-floating">
              <span class="badge ${riskClass}">${rep.risk_level || 'LOW'}</span>
            </div>
            <div class="report-status-floating">
              <span class="status-badge">${rep.status || 'REPORTED'}</span>
            </div>
          </div>
          <div class="report-card-body">
            <div class="report-id">${rep.report_id || 'ID Pending'}</div>
            <div class="report-title">${rep.animal_type} Rescue</div>
            <div class="report-location">
              📍 <span>${this.escapeHtml(rep.location_address || 'Address provided')}</span>
            </div>
            <div class="report-desc-snip">
              ${this.escapeHtml(rep.description || 'No description provided.')}
            </div>
          </div>
          <div class="report-card-footer">
            <span class="report-time">🕒 ${relativeTime}</span>
            <button class="btn btn-outline btn-sm" onclick="App.openDetailModal('${rep.report_id}')">
              Manage & Details
            </button>
          </div>
        </div>
      `;
    }).join('');
  },

  openDetailModal(reportId) {
    const rep = this.cachedReports.find(r => r.report_id === reportId);
    if (!rep) return;

    const modal = document.getElementById('modal-detail');
    document.getElementById('detail-id').textContent = rep.report_id;
    document.getElementById('detail-title').textContent = `${rep.animal_type} Rescue Details`;
    
    const riskBadge = document.getElementById('detail-risk-badge');
    riskBadge.textContent = `${rep.risk_level} Priority (Score: ${rep.risk_score || 0})`;
    riskBadge.className = `badge badge-${(rep.risk_level || 'LOW').toLowerCase()}`;

    document.getElementById('detail-location').textContent = rep.location_address || 'N/A';
    document.getElementById('detail-coordinates').textContent = (rep.latitude && rep.longitude) ? `${rep.latitude}, ${rep.longitude}` : 'No GPS coordinates';
    document.getElementById('detail-condition').textContent = rep.condition || 'N/A';
    document.getElementById('detail-symptoms').textContent = (rep.symptoms && rep.symptoms.length > 0) ? rep.symptoms.join(', ') : 'None specified';
    document.getElementById('detail-description').textContent = rep.description || 'N/A';
    document.getElementById('detail-reporter').textContent = `${rep.reporter_name || 'Anonymous'} (${rep.reporter_phone || 'No phone'})`;
    document.getElementById('detail-created').textContent = new Date(rep.created_at).toLocaleString();

    const photoEl = document.getElementById('detail-photo');
    const photoSrc = rep.photo_url || rep.photo_data;
    if (photoSrc) {
      photoEl.src = photoSrc;
      photoEl.style.display = 'block';
    } else {
      photoEl.style.display = 'none';
    }

    // Status select
    const statusSelect = document.getElementById('detail-select-status');
    statusSelect.value = rep.status || 'REPORTED';

    // Update Action Button
    const saveBtn = document.getElementById('btn-save-status');
    saveBtn.onclick = async () => {
      const newStatus = statusSelect.value;
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="spinner"></span> Updating...';

      try {
        await API.updateReportStatus(rep.report_id, { status: newStatus });
        rep.status = newStatus;
        this.showToast(`Status updated to ${newStatus}`, 'success');
        this.updateKpiCounters(this.cachedReports);
        this.applyDashboardFilters();
        modal.classList.remove('open');
      } catch (err) {
        this.showToast(`Update failed: ${err.message}`, 'error');
      } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = 'Save Status';
      }
    };

    modal.classList.add('open');
  },

  // ------------------------------------------------------------------------
  // Settings & API Configuration Modal
  // ------------------------------------------------------------------------
  bindSettingsModal() {
    const pill = document.getElementById('api-status-pill');
    const modal = document.getElementById('modal-settings');
    const closeBtns = document.querySelectorAll('.modal-close, .modal-cancel');
    const saveBtn = document.getElementById('btn-save-api-url');
    const urlInput = document.getElementById('input-api-endpoint');

    if (pill) {
      pill.addEventListener('click', () => {
        urlInput.value = API.getBaseUrl();
        modal.classList.add('open');
      });
    }

    closeBtns.forEach(b => {
      b.addEventListener('click', () => {
        document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('open'));
      });
    });

    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const newUrl = urlInput.value.trim();
        API.setBaseUrl(newUrl);
        modal.classList.remove('open');
        this.showToast('API Endpoint updated', 'info');
        await this.checkApiStatus();
        this.loadDashboardData();
      });
    }
  },

  async checkApiStatus() {
    const pill = document.getElementById('api-status-pill');
    const text = document.getElementById('api-status-text');
    const dot = document.getElementById('api-status-dot');

    if (!pill) return;

    const isConnected = await API.ping();
    const isCloud = API.getBaseUrl().includes('amazonaws.com');

    if (isConnected) {
      dot.className = isCloud ? 'status-dot cloud' : 'status-dot online';
      text.textContent = isCloud ? 'AWS Cloud Connected' : 'Local Server Active';
    } else {
      dot.className = 'status-dot offline';
      text.textContent = API.getBaseUrl() ? 'Cloud Offline (Using Cache)' : 'Local Mode';
    }
  },

  // ------------------------------------------------------------------------
  // Helpers & Toast Notifications
  // ------------------------------------------------------------------------
  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const iconMap = { success: '✅', error: '⚠️', info: 'ℹ️' };
    toast.innerHTML = `<span>${iconMap[type] || 'ℹ️'}</span> <span>${this.escapeHtml(message)}</span>`;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },

  formatRelativeTime(isoString) {
    if (!isoString) return 'Just now';
    const date = new Date(isoString);
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);

    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  },

  escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }
};

window.App = App;
window.viewReportModal = (id) => App.openDetailModal(id);
