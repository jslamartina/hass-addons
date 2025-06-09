const BASE_PATH = '/'
const toast = document.getElementById('toast');

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 4000);
}

function showError(message) {
  const err = document.getElementById('error');
  err.textContent = message;
  err.classList.remove('hidden');
  setTimeout(() => err.classList.add('hidden'), 3000);
}

function focusOTP() {
  const otpField = document.getElementById('otpInput');
  otpField.focus();
  otpField.select();
}

async function startExport() {
  const btn = document.getElementById('startButton');
  const txt = document.getElementById('startText');
  const spinner = document.getElementById('spinner');
  btn.disabled = true;
  txt.textContent = 'Exporting...';
  spinner.classList.remove('hidden');

  try {
    const response = await fetch('/api/export/start');
    const result = await response.json();

    if (response.ok && result.success) {
      await fetchAndShowConfig();
    } else if (response.ok && result.message?.includes("OTP")) {
      showToast(result.message);
      focusOTP();
    } else {
      showError(result.detail || 'Export failed.');
    }
  } catch (e) {
    showError('Export error: ' + e.message);
  } finally {
    btn.disabled = false;
    txt.textContent = 'Start Export';
    spinner.classList.add('hidden');
  }
}

async function submitOTP() {
  const otp = document.getElementById('otpInput').value.trim();
  if (!/^[0-9]{4,10}$/.test(otp)) return showError("OTP must be 4–10 digits");

  try {
    const response = await fetch('/api/export/otp/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ otp: parseInt(otp, 10) })
    });
    const result = await response.json();

    if (response.ok && result.success) {
      showToast("OTP accepted, loading config...");
      await fetchAndShowConfig();
    } else {
      showError(result.detail || 'OTP failed.');
    }
  } catch (e) {
    showError('OTP submit error: ' + e.message);
  }
}

async function requestOTP() {
  try {
    const response = await fetch('/api/export/otp/request');
    const result = await response.json();
    if (!result.success) {
      showToast(result.message || "OTP requested.");
      focusOTP();
    }
  } catch (e) {
    showError('OTP request error: ' + e.message);
  }
}

async function fetchAndShowConfig() {
  try {
    const response = await fetch('/api/export/download');
    const text = await response.text();
    const pre = document.querySelector('#yamlPreview code');
    pre.textContent = text;
    Prism.highlightElement(pre);
    document.getElementById('downloadLink').href = '/api/export/download';
    document.getElementById('successSection').classList.remove('hidden');
  } catch (e) {
    showError("Failed to load config: " + e.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById('otpInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') submitOTP();
  });
});
