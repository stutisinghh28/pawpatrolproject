/**
 * PawPatrol API Service
 * Handles unified communication with either:
 *  1. Local Python Development Server (http://localhost:8000/api)
 *  2. AWS Lambda HTTPS Endpoint (Function URL / API Gateway)
 *  3. In-browser offline LocalStorage fallback for instant zero-dependency testing
 */

const API = {
  // Default base URL. If empty, uses relative path (works on local server).
  // Can be overridden in settings modal with the AWS Lambda Function URL.
  baseUrl: localStorage.getItem('pawpatrol_api_url') || '',

  setBaseUrl(url) {
    this.baseUrl = url.trim().replace(/\/+$/, '');
    localStorage.setItem('pawpatrol_api_url', this.baseUrl);
  },

  getBaseUrl() {
    return this.baseUrl;
  },

  // Check health / connectivity
  async ping() {
    try {
      const url = this.baseUrl ? `${this.baseUrl}/reports` : '/api/reports';
      const res = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
      return res.ok;
    } catch (e) {
      return false;
    }
  },

  // Submit a new rescue report
  async createReport(reportData) {
    const url = this.baseUrl ? `${this.baseUrl}/reports` : '/api/reports';
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reportData)
      });
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Server returned ${res.status}: ${errorText}`);
      }
      return await res.json();
    } catch (err) {
      console.warn('API call failed, falling back to LocalStorage:', err.message);
      return this._fallbackCreateReport(reportData);
    }
  },

  // Fetch all reports with optional filters
  async getReports(filters = {}) {
    const params = new URLSearchParams();
    if (filters.risk_level && filters.risk_level !== 'ALL') params.append('risk_level', filters.risk_level);
    if (filters.status && filters.status !== 'ALL') params.append('status', filters.status);
    if (filters.animal_type && filters.animal_type !== 'ALL') params.append('animal_type', filters.animal_type);

    const queryString = params.toString() ? `?${params.toString()}` : '';
    const url = this.baseUrl ? `${this.baseUrl}/reports${queryString}` : `/api/reports${queryString}`;

    try {
      const res = await fetch(url, {
        method: 'GET',
        headers: { 'Accept': 'application/json' }
      });
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.warn('API call failed, fetching from LocalStorage:', err.message);
      return this._fallbackGetReports(filters);
    }
  },

  // Update report status (e.g., Reported -> In Progress -> Rescued)
  async updateReportStatus(reportId, updates) {
    const url = this.baseUrl ? `${this.baseUrl}/reports/${reportId}` : `/api/reports/${reportId}`;
    try {
      const res = await fetch(url, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.warn('API call failed, updating LocalStorage:', err.message);
      return this._fallbackUpdateReport(reportId, updates);
    }
  },

  // Request S3 Pre-signed URL for direct secure photo upload
  async getUploadUrl(filename, contentType) {
    const url = this.baseUrl ? `${this.baseUrl}/upload-url` : '/api/upload-url';
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, content_type: contentType })
      });
      if (!res.ok) throw new Error('Could not get pre-signed upload URL');
      return await res.json();
    } catch (err) {
      console.warn('Pre-signed URL request failed (using direct/base64 upload):', err.message);
      return null;
    }
  },

  // ------------------------------------------------------------------------
  // Browser LocalStorage Fallbacks (Ensures 100% demo continuity offline)
  // ------------------------------------------------------------------------
  _getStoredReports() {
    try {
      return JSON.parse(localStorage.getItem('pawpatrol_local_reports') || '[]');
    } catch (e) {
      return [];
    }
  },

  _saveStoredReports(reports) {
    localStorage.setItem('pawpatrol_local_reports', JSON.stringify(reports));
  },

  _fallbackCreateReport(reportData) {
    const reports = this._getStoredReports();
    const newReport = {
      ...reportData,
      report_id: `PAW-${Date.now().toString(36).toUpperCase()}-${Math.floor(1000 + Math.random() * 9000)}`,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      status: 'REPORTED',
      _storage: 'offline_local_storage'
    };
    reports.unshift(newReport);
    this._saveStoredReports(reports);
    return { success: true, report: newReport, offline: true };
  },

  _fallbackGetReports(filters) {
    let reports = this._getStoredReports();
    if (filters.risk_level && filters.risk_level !== 'ALL') {
      reports = reports.filter(r => r.risk_level === filters.risk_level);
    }
    if (filters.status && filters.status !== 'ALL') {
      reports = reports.filter(r => r.status === filters.status);
    }
    if (filters.animal_type && filters.animal_type !== 'ALL') {
      reports = reports.filter(r => r.animal_type === filters.animal_type);
    }
    return { success: true, reports: reports, count: reports.length, offline: true };
  },

  _fallbackUpdateReport(reportId, updates) {
    const reports = this._getStoredReports();
    const idx = reports.findIndex(r => r.report_id === reportId);
    if (idx !== -1) {
      reports[idx] = { ...reports[idx], ...updates, updated_at: new Date().toISOString() };
      this._saveStoredReports(reports);
      return { success: true, report: reports[idx], offline: true };
    }
    throw new Error('Report not found in local storage');
  }
};

window.API = API;
