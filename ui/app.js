/**
 * ui/app.js
 * ---------
 * NEHA Desktop UI Controller & State Orchestrator.
 * Connects the voice-first orb frontend to the Python backend via pywebview JS-API bridge.
 */

(function () {
  'use strict';

  // Application State
  const AppState = {
    state: 'hands_free_off',
    handsfreeActive: false,
    voiceEnabled: true,
    ttsProvider: 'sarvam',
    micDevice: '',
    recordingDuration: 8,
    silenceThreshold: 300,
    activeModel: '',
    sttModel: '',
    sarvamVoice: '',
    wakeWordStatus: { available: false },
    vadSettings: {
      silence_duration: 1.3,
      follow_up_timeout: 4.5,
      speech_start_timeout: 6.0
    },
    drawerOpen: false,
    unreadMessages: false,
    recTimerInterval: null,
    recElapsedSeconds: 0,
    recMaxSeconds: 8
  };

  // DOM Elements
  const DOM = {
    // Header
    headerModelPill: document.getElementById('header-model-pill'),
    headerProviderPill: document.getElementById('header-provider-pill'),
    btnQuickVoiceToggle: document.getElementById('btn-quick-voice-toggle'),
    headerVoiceIcon: document.getElementById('header-voice-icon'),
    headerVoiceText: document.getElementById('header-voice-text'),
    btnOpenChatDrawer: document.getElementById('btn-open-chat-drawer'),
    chatUnreadDot: document.getElementById('chat-unread-dot'),
    btnOpenSettings: document.getElementById('btn-open-settings'),

    // Hero Stage
    mainStatusDot: document.getElementById('main-status-dot'),
    mainStatusTag: document.getElementById('main-status-tag'),
    presenceStateTitle: document.getElementById('presence-state-title'),
    presenceStateDesc: document.getElementById('presence-state-desc'),
    btnToggleHandsfree: document.getElementById('btn-toggle-handsfree'),
    handsfreeBtnText: document.getElementById('handsfree-btn-text'),
    handsfreeBtnHint: document.getElementById('handsfree-btn-hint'),
    handsfreeStatePill: document.getElementById('handsfree-state-pill'),
    handsfreeMicWave: document.getElementById('handsfree-mic-wave'),
    btnManualMic: document.getElementById('btn-manual-mic'),
    btnStopSpeechHero: document.getElementById('btn-stop-speech-hero'),
    micPrivacyNotice: document.getElementById('mic-privacy-notice'),

    // Manual Recording & Review Fallbacks
    recordingBar: document.getElementById('recording-bar'),
    recordingTimer: document.getElementById('recording-timer'),
    btnFinishRecording: document.getElementById('btn-finish-recording'),
    btnCancelRecording: document.getElementById('btn-cancel-recording'),
    reviewCard: document.getElementById('review-card'),
    reviewTextarea: document.getElementById('review-textarea'),
    btnReviewSend: document.getElementById('btn-review-send'),
    btnReviewRecordAgain: document.getElementById('btn-review-record-again'),
    btnReviewDiscard: document.getElementById('btn-review-discard'),

    // Chat History Drawer
    chatHistoryDrawer: document.getElementById('chat-history-drawer'),
    drawerBackdrop: document.getElementById('drawer-backdrop'),
    btnCloseDrawer: document.getElementById('btn-close-drawer'),
    btnDrawerNewChat: document.getElementById('btn-drawer-new-chat'),
    messagesContainer: document.getElementById('messages-container'),
    emptyState: document.getElementById('empty-state'),
    composerInput: document.getElementById('composer-input'),
    btnSend: document.getElementById('btn-send'),

    // Wake Setup Modal
    wakeSetupModal: document.getElementById('wake-setup-modal'),
    btnCloseWakeSetup: document.getElementById('btn-close-wake-setup'),
    btnWakeSetupOk: document.getElementById('btn-wake-setup-ok'),
    linkPicovoiceConsole: document.getElementById('link-picovoice-console'),

    // Settings Modal
    settingsModal: document.getElementById('settings-modal'),
    btnCloseSettings: document.getElementById('btn-close-settings'),
    settingVoiceEnabled: document.getElementById('setting-voice-enabled'),
    settingTtsProvider: document.getElementById('setting-tts-provider'),
    settingMicDevice: document.getElementById('setting-mic-device'),
    btnRefreshMics: document.getElementById('btn-refresh-mics'),
    settingVadSilence: document.getElementById('setting-vad-silence'),
    valVadSilence: document.getElementById('val-vad-silence'),
    settingVadFollowup: document.getElementById('setting-vad-followup'),
    valVadFollowup: document.getElementById('val-vad-followup'),
    diagChatModel: document.getElementById('diag-chat-model'),
    diagSttModel: document.getElementById('diag-stt-model'),
    diagWakeStatus: document.getElementById('diag-wake-status'),
    diagSarvamVoice: document.getElementById('diag-sarvam-voice'),

    // Toasts
    toastContainer: document.getElementById('toast-container')
  };

  // Initialize Canvas Orb visualizer
  let orbInstance = null;
  if (typeof NehaOrb !== 'undefined') {
    orbInstance = new NehaOrb('neha-orb-canvas');
  }

  // ----------------------------------------------------------------------------
  // Helper Utilities: Sanitization, Markdown Formatting, Toasts
  // ----------------------------------------------------------------------------

  function escapeHtml(text) {
    if (!text) return '';
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
  }

  function formatMessageText(rawText) {
    if (!rawText) return '';
    let escaped = escapeHtml(rawText);

    // Code blocks ```lang\ncode\n```
    const codeBlockRegex = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
    escaped = escaped.replace(codeBlockRegex, (match, lang, code) => {
      const displayLang = lang ? lang.toUpperCase() : 'CODE';
      return `
        <div style="margin: 10px 0;">
          <div class="code-header">
            <span>${displayLang}</span>
            <button class="btn-copy-code" onclick="window.copyCodeBlock(this)">Copy</button>
          </div>
          <pre class="code-block"><code>${code.trim()}</code></pre>
        </div>
      `;
    });

    // Inline code `code`
    escaped = escaped.replace(/`([^`]+)`/g, '<code style="background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 0.85em;">$1</code>');

    // Bold **text**
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Paragraphs
    const paragraphs = escaped.split(/\n\s*\n/);
    return paragraphs.map(p => {
      if (p.includes('<pre class="code-block">')) return p;
      return `<p style="margin-bottom: 8px;">${p.replace(/\n/g, '<br>')}</p>`;
    }).join('');
  }

  window.copyCodeBlock = function (btn) {
    const pre = btn.closest('div').parentElement.querySelector('code');
    if (!pre) return;
    const codeText = pre.innerText || pre.textContent;
    navigator.clipboard.writeText(codeText).then(() => {
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => { btn.textContent = orig; }, 2000);
    }).catch(err => console.warn('Copy failed:', err));
  };

  function showToast(message, type = 'notice', duration = 4000) {
    if (!DOM.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    DOM.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // ----------------------------------------------------------------------------
  // UI State Machine & Visuals
  // ----------------------------------------------------------------------------

  function setApplicationState(newState, extraData = {}) {
    AppState.state = newState;

    if (orbInstance) {
      orbInstance.setState(newState);
    }

    // Stop button visibility: only while speaking
    if (newState === 'speaking') {
      DOM.btnStopSpeechHero.classList.add('visible');
    } else {
      DOM.btnStopSpeechHero.classList.remove('visible');
    }

    // Reset manual recording timer if state changed away from recording
    if (newState !== 'recording' && AppState.recTimerInterval) {
      clearInterval(AppState.recTimerInterval);
      AppState.recTimerInterval = null;
    }

    switch (newState) {
      case 'hands_free_off':
      case 'idle':
        AppState.handsfreeActive = false;
        DOM.mainStatusDot.className = 'status-indicator-dot';
        DOM.mainStatusTag.textContent = 'Hands-Free Off';
        DOM.presenceStateTitle.textContent = 'NEHA';
        DOM.presenceStateDesc.textContent = extraData.message || 'Hands-free is disabled. Enable below or click to talk.';
        DOM.btnToggleHandsfree.className = 'btn-handsfree';
        DOM.handsfreeBtnText.textContent = 'Enable Hands-Free';
        DOM.handsfreeBtnHint.textContent = 'Listen for “Hi NEHA”';
        DOM.handsfreeStatePill.className = 'handsfree-status-pill off';
        DOM.handsfreeStatePill.textContent = 'OFF';
        DOM.recordingBar.classList.remove('active');
        DOM.reviewCard.classList.remove('active');
        break;

      case 'waiting_for_wake':
        AppState.handsfreeActive = true;
        DOM.mainStatusDot.className = 'status-indicator-dot active';
        DOM.mainStatusTag.textContent = 'Listening for Wake-Word';
        DOM.presenceStateTitle.textContent = 'Waiting for “Hi NEHA”';
        DOM.presenceStateDesc.textContent = extraData.notice || 'Local detector is active. Say “Hi NEHA” to start speaking.';
        DOM.btnToggleHandsfree.className = 'btn-handsfree active';
        DOM.handsfreeBtnText.textContent = 'Hands-Free Active';
        DOM.handsfreeBtnHint.textContent = 'Listening for “Hi NEHA”';
        DOM.handsfreeStatePill.className = 'handsfree-status-pill on';
        DOM.handsfreeStatePill.textContent = 'MIC ON';
        DOM.recordingBar.classList.remove('active');
        DOM.reviewCard.classList.remove('active');
        break;

      case 'acknowledging':
        DOM.mainStatusDot.className = 'status-indicator-dot listening';
        DOM.mainStatusTag.textContent = 'Wake Detected';
        DOM.presenceStateTitle.textContent = '“Haan Rocky, bolo”';
        DOM.presenceStateDesc.textContent = 'Acknowledging wake word. Listening starts in a moment...';
        DOM.btnToggleHandsfree.className = 'btn-handsfree listening';
        DOM.handsfreeStatePill.className = 'handsfree-status-pill listening';
        DOM.handsfreeStatePill.textContent = 'WAKE';
        break;

      case 'listening':
        DOM.mainStatusDot.className = 'status-indicator-dot listening';
        DOM.mainStatusTag.textContent = 'Listening to Question';
        DOM.presenceStateTitle.textContent = 'Listening...';
        DOM.presenceStateDesc.textContent = extraData.message || 'Voice Activity Detection active. Boliye apna question...';
        DOM.btnToggleHandsfree.className = 'btn-handsfree listening';
        DOM.handsfreeStatePill.className = 'handsfree-status-pill listening';
        DOM.handsfreeStatePill.textContent = 'LISTENING';
        break;

      case 'recording':
        DOM.mainStatusDot.className = 'status-indicator-dot listening';
        DOM.mainStatusTag.textContent = 'Speech In Progress';
        DOM.presenceStateTitle.textContent = 'Recording Speech';
        DOM.presenceStateDesc.textContent = 'Microphone capturing speech. Stop speaking when finished.';
        DOM.btnToggleHandsfree.className = 'btn-handsfree listening';
        DOM.handsfreeStatePill.className = 'handsfree-status-pill listening';
        DOM.handsfreeStatePill.textContent = 'RECORDING';
        if (extraData.duration) {
          DOM.recordingBar.classList.add('active');
          startRecordingTimer(extraData.duration);
        }
        break;

      case 'transcribing':
        DOM.mainStatusDot.className = 'status-indicator-dot busy';
        DOM.mainStatusTag.textContent = 'Transcribing';
        DOM.presenceStateTitle.textContent = 'Transcribing Speech...';
        DOM.presenceStateDesc.textContent = `Groq Whisper STT (${AppState.sttModel || 'turbo'}) processing audio...`;
        DOM.recordingBar.classList.remove('active');
        break;

      case 'reviewing':
        DOM.mainStatusDot.className = 'status-indicator-dot';
        DOM.mainStatusTag.textContent = 'Review Transcript';
        DOM.presenceStateTitle.textContent = 'Speech Recognized';
        DOM.presenceStateDesc.textContent = 'Review transcript before sending to NEHA.';
        DOM.reviewCard.classList.add('active');
        if (extraData.transcript) {
          DOM.reviewTextarea.value = extraData.transcript;
          DOM.reviewTextarea.focus();
        }
        break;

      case 'thinking':
      case 'generating':
        DOM.mainStatusDot.className = 'status-indicator-dot busy';
        DOM.mainStatusTag.textContent = 'Thinking';
        DOM.presenceStateTitle.textContent = 'NEHA is thinking...';
        DOM.presenceStateDesc.textContent = `Groq Llama-3 (${AppState.activeModel}) generating response...`;
        break;

      case 'speaking':
        DOM.mainStatusDot.className = 'status-indicator-dot busy';
        DOM.mainStatusTag.textContent = 'Speaking';
        DOM.presenceStateTitle.textContent = 'Speaking Response';
        DOM.presenceStateDesc.textContent = AppState.ttsProvider === 'sarvam'
          ? `Sarvam AI Bulbul (${AppState.sarvamVoice}) speech playback...`
          : 'Local SAPI5 speech playback...';
        break;

      case 'follow_up':
        DOM.mainStatusDot.className = 'status-indicator-dot listening';
        DOM.mainStatusTag.textContent = 'Follow-Up Window';
        DOM.presenceStateTitle.textContent = 'Listening for Follow-Up...';
        DOM.presenceStateDesc.textContent = extraData.message || 'Boliye agar koi follow-up sawaal hai, ya shaant rahein to return to wake waiting.';
        DOM.btnToggleHandsfree.className = 'btn-handsfree active';
        DOM.handsfreeStatePill.className = 'handsfree-status-pill listening';
        DOM.handsfreeStatePill.textContent = 'FOLLOW-UP';
        break;

      case 'error':
        DOM.mainStatusDot.className = 'status-indicator-dot';
        DOM.mainStatusTag.textContent = 'Notice';
        DOM.presenceStateTitle.textContent = 'NEHA Notice';
        DOM.presenceStateDesc.textContent = extraData.error || extraData.notice || 'An error occurred.';
        if (extraData.error) showToast(extraData.error, 'error');
        break;
    }
  }

  function startRecordingTimer(maxDuration) {
    AppState.recElapsedSeconds = 0;
    AppState.recMaxSeconds = maxDuration;
    updateRecordingTimerDisplay();

    if (AppState.recTimerInterval) clearInterval(AppState.recTimerInterval);
    AppState.recTimerInterval = setInterval(() => {
      AppState.recElapsedSeconds += 1;
      updateRecordingTimerDisplay();
      if (AppState.recElapsedSeconds >= AppState.recMaxSeconds) {
        clearInterval(AppState.recTimerInterval);
        AppState.recTimerInterval = null;
      }
    }, 1000);
  }

  function updateRecordingTimerDisplay() {
    const pad = n => String(n).padStart(2, '0');
    DOM.recordingTimer.textContent = `00:${pad(AppState.recElapsedSeconds)} / 00:${pad(AppState.recMaxSeconds)}s`;
  }

  // ----------------------------------------------------------------------------
  // Chat History Drawer & Messages
  // ----------------------------------------------------------------------------

  function openChatDrawer() {
    AppState.drawerOpen = true;
    DOM.chatHistoryDrawer.classList.add('open');
    DOM.drawerBackdrop.classList.add('active');
    DOM.chatUnreadDot.classList.remove('active');
    AppState.unreadMessages = false;
    DOM.composerInput.focus();
    scrollChatToBottom();
  }

  function closeChatDrawer() {
    AppState.drawerOpen = false;
    DOM.chatHistoryDrawer.classList.remove('open');
    DOM.drawerBackdrop.classList.remove('active');
  }

  function scrollChatToBottom() {
    setTimeout(() => {
      DOM.messagesContainer.scrollTop = DOM.messagesContainer.scrollHeight;
    }, 40);
  }

  function appendChatMessage(role, content, options = {}) {
    if (DOM.emptyState && DOM.emptyState.parentElement) {
      DOM.emptyState.remove();
    }

    const row = document.createElement('div');
    row.className = `message-row ${role}`;

    const tag = document.createElement('div');
    tag.className = 'message-tag';
    if (role === 'user') {
      const isVoice = options.source === 'voice_handsfree';
      tag.innerHTML = isVoice
        ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path></svg> Voice Input`
        : `Typed`;
    } else {
      tag.textContent = 'NEHA';
    }

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = formatMessageText(content);

    row.appendChild(tag);
    row.appendChild(bubble);
    DOM.messagesContainer.appendChild(row);

    scrollChatToBottom();

    // If drawer is closed, trigger unread indicator dot
    if (!AppState.drawerOpen) {
      AppState.unreadMessages = true;
      DOM.chatUnreadDot.classList.add('active');
    }
  }

  // ----------------------------------------------------------------------------
  // Bridge Callbacks & Events
  // ----------------------------------------------------------------------------

  window.__neha_on_event = function (payload) {
    if (!payload || !payload.event) return;
    const { event, data } = payload;

    switch (event) {
      case 'state_change':
        setApplicationState(data.state, data);
        break;

      case 'user_message':
        appendChatMessage('user', data.content, { source: data.source });
        break;

      case 'response_received':
        appendChatMessage('assistant', data.content, { is_error: data.is_error });
        break;

      case 'conversation_cleared':
        DOM.messagesContainer.innerHTML = `
          <div class="empty-state" id="empty-state">
            <div class="empty-state-badge">SESSION MEMORY CLEARED</div>
            <h4>Fresh Conversation</h4>
            <p>Aapki pichli session conversation reset ho chuki hai. Naya question puchiye.</p>
          </div>
        `;
        showToast('Conversation memory cleared.', 'notice');
        break;
    }
  };

  // ----------------------------------------------------------------------------
  // Initialization & Pywebview Bridge Handshake
  // ----------------------------------------------------------------------------

  function initBridge() {
    if (!window.pywebview || !window.pywebview.api) {
      setTimeout(initBridge, 100);
      return;
    }

    window.pywebview.api.get_initial_state().then(state => {
      AppState.voiceEnabled = state.voice_enabled;
      AppState.ttsProvider = state.tts_provider;
      AppState.micDevice = state.mic_device;
      AppState.activeModel = state.active_model;
      AppState.sttModel = state.stt_model;
      AppState.sarvamVoice = state.sarvam_voice;
      AppState.handsfreeActive = state.handsfree_active;
      AppState.wakeWordStatus = state.wake_word_status || {};
      AppState.vadSettings = state.vad_settings || AppState.vadSettings;

      // Update UI elements
      DOM.headerModelPill.textContent = state.activeModel || 'Groq Llama-3';
      DOM.headerProviderPill.textContent = state.tts_provider === 'sarvam' ? 'Sarvam Bulbul' : 'Local SAPI5';
      updateVoiceToggleUI(state.voice_enabled);

      // Populate Settings Diagnostics
      DOM.diagChatModel.textContent = state.active_model || 'llama-3.3-70b-versatile';
      DOM.diagSttModel.textContent = `Whisper (${state.stt_model || 'whisper-large-v3-turbo'})`;
      DOM.diagSarvamVoice.textContent = state.sarvam_voice || 'neha';
      DOM.diagWakeStatus.textContent = AppState.wakeWordStatus.configured ? 'Configured (Local)' : 'Setup Required';

      // Setting Inputs
      DOM.settingVoiceEnabled.checked = state.voice_enabled;
      DOM.settingTtsProvider.value = state.tts_provider;
      DOM.settingVadSilence.value = AppState.vadSettings.silence_duration || 1.3;
      DOM.valVadSilence.textContent = `${DOM.settingVadSilence.value}s`;
      DOM.settingVadFollowup.value = AppState.vadSettings.follow_up_timeout || 4.5;
      DOM.valVadFollowup.textContent = `${DOM.settingVadFollowup.value}s`;

      // Set initial state
      setApplicationState(state.state || (AppState.handsfreeActive ? 'waiting_for_wake' : 'hands_free_off'));

      // Populate Microphone Devices
      populateMicDevices();
    }).catch(err => {
      console.warn('Initial state fetch error:', err);
    });
  }

  function updateVoiceToggleUI(enabled) {
    AppState.voiceEnabled = enabled;
    if (enabled) {
      DOM.headerVoiceText.textContent = 'Voice ON';
      DOM.btnQuickVoiceToggle.style.borderColor = 'rgba(16, 185, 129, 0.4)';
    } else {
      DOM.headerVoiceText.textContent = 'Voice Muted';
      DOM.btnQuickVoiceToggle.style.borderColor = 'rgba(244, 63, 94, 0.4)';
    }
  }

  function populateMicDevices() {
    if (!window.pywebview || !window.pywebview.api) return;
    window.pywebview.api.get_mic_devices().then(devices => {
      DOM.settingMicDevice.innerHTML = '<option value="">Default (System Input)</option>';
      if (Array.isArray(devices)) {
        devices.forEach(dev => {
          const opt = document.createElement('option');
          opt.value = dev.index;
          opt.textContent = `${dev.name} [${dev.index}]`;
          if (String(dev.index) === String(AppState.micDevice)) {
            opt.selected = true;
          }
          DOM.settingMicDevice.appendChild(opt);
        });
      }
    }).catch(err => console.warn('Failed to load mic devices:', err));
  }

  // ----------------------------------------------------------------------------
  // Interactive Event Listeners
  // ----------------------------------------------------------------------------

  // Hands-Free Toggle
  DOM.btnToggleHandsfree.addEventListener('click', () => {
    if (!window.pywebview || !window.pywebview.api) return;
    const shouldEnable = !AppState.handsfreeActive;

    window.pywebview.api.toggle_handsfree(shouldEnable).then(res => {
      if (res.status === 'ok') {
        AppState.handsfreeActive = shouldEnable;
        showToast(shouldEnable ? 'Hands-free mode enabled.' : 'Hands-free mode disabled.', 'notice');
      } else {
        // Missing configuration (AccessKey or .ppn model) -> Display Setup Modal
        DOM.wakeSetupModal.classList.add('active');
      }
    }).catch(err => {
      showToast(`Hands-free error: ${err}`, 'error');
    });
  });

  // Manual Click-to-Talk Mic Button
  DOM.btnManualMic.addEventListener('click', () => {
    if (!window.pywebview || !window.pywebview.api) return;
    if (AppState.state === 'recording') {
      window.pywebview.api.stop_recording_early();
    } else {
      window.pywebview.api.start_recording().catch(err => showToast(`Mic error: ${err}`, 'error'));
    }
  });

  // Stop Speech Control
  DOM.btnStopSpeechHero.addEventListener('click', () => {
    if (!window.pywebview || !window.pywebview.api) return;
    window.pywebview.api.stop_speech();
  });

  // Manual Recording Finish/Cancel
  DOM.btnFinishRecording.addEventListener('click', () => {
    if (window.pywebview && window.pywebview.api) window.pywebview.api.stop_recording_early();
  });

  DOM.btnCancelRecording.addEventListener('click', () => {
    if (window.pywebview && window.pywebview.api) window.pywebview.api.cancel_recording();
  });

  // Manual Review Card Actions
  DOM.btnReviewSend.addEventListener('click', () => {
    const text = DOM.reviewTextarea.value.trim();
    if (!text) return;
    DOM.reviewCard.classList.remove('active');
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.send_message(text);
    }
  });

  DOM.btnReviewDiscard.addEventListener('click', () => {
    DOM.reviewCard.classList.remove('active');
    setApplicationState('idle');
  });

  DOM.btnReviewRecordAgain.addEventListener('click', () => {
    DOM.reviewCard.classList.remove('active');
    if (window.pywebview && window.pywebview.api) window.pywebview.api.start_recording();
  });

  // Chat Drawer Open/Close
  DOM.btnOpenChatDrawer.addEventListener('click', openChatDrawer);
  DOM.btnCloseDrawer.addEventListener('click', closeChatDrawer);
  DOM.drawerBackdrop.addEventListener('click', closeChatDrawer);

  // New Chat in Drawer
  DOM.btnDrawerNewChat.addEventListener('click', () => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.new_conversation();
    }
  });

  // Composer Typing
  function handleSendMessage() {
    const text = DOM.composerInput.value.trim();
    if (!text) return;
    DOM.composerInput.value = '';
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.send_message(text);
    }
  }

  DOM.btnSend.addEventListener('click', handleSendMessage);
  DOM.composerInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  });

  // Quick Voice Mute Toggle
  DOM.btnQuickVoiceToggle.addEventListener('click', () => {
    const newVoice = !AppState.voiceEnabled;
    updateVoiceToggleUI(newVoice);
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.update_settings({ voice_enabled: newVoice });
    }
  });

  // Settings Modal Open/Close
  DOM.btnOpenSettings.addEventListener('click', () => {
    DOM.settingsModal.classList.add('active');
  });

  DOM.btnCloseSettings.addEventListener('click', () => {
    DOM.settingsModal.classList.remove('active');
  });

  DOM.btnRefreshMics.addEventListener('click', populateMicDevices);

  // Wake Setup Modal Open/Close
  DOM.btnCloseWakeSetup.addEventListener('click', () => {
    DOM.wakeSetupModal.classList.remove('active');
  });

  DOM.btnWakeSetupOk.addEventListener('click', () => {
    DOM.wakeSetupModal.classList.remove('active');
  });

  DOM.linkPicovoiceConsole.addEventListener('click', (e) => {
    e.preventDefault();
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.open_external_url('https://console.picovoice.ai/');
    }
  });

  // Settings Dynamic Input Handlers
  DOM.settingVoiceEnabled.addEventListener('change', (e) => {
    updateVoiceToggleUI(e.target.checked);
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.update_settings({ voice_enabled: e.target.checked });
    }
  });

  DOM.settingTtsProvider.addEventListener('change', (e) => {
    AppState.ttsProvider = e.target.value;
    DOM.headerProviderPill.textContent = e.target.value === 'sarvam' ? 'Sarvam Bulbul' : 'Local SAPI5';
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.update_settings({ tts_provider: e.target.value });
    }
  });

  DOM.settingMicDevice.addEventListener('change', (e) => {
    AppState.micDevice = e.target.value;
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.update_settings({ mic_device: e.target.value });
    }
  });

  DOM.settingVadSilence.addEventListener('input', (e) => {
    DOM.valVadSilence.textContent = `${e.target.value}s`;
  });

  DOM.settingVadSilence.addEventListener('change', (e) => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.update_settings({ silence_duration: parseFloat(e.target.value) });
    }
  });

  DOM.settingVadFollowup.addEventListener('input', (e) => {
    DOM.valVadFollowup.textContent = `${e.target.value}s`;
  });

  DOM.settingVadFollowup.addEventListener('change', (e) => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.update_settings({ follow_up_timeout: parseFloat(e.target.value) });
    }
  });

  // Keyboard Shortcuts
  window.addEventListener('keydown', (e) => {
    // Esc closes modals and drawer
    if (e.key === 'Escape') {
      if (DOM.wakeSetupModal.classList.contains('active')) {
        DOM.wakeSetupModal.classList.remove('active');
      } else if (DOM.settingsModal.classList.contains('active')) {
        DOM.settingsModal.classList.remove('active');
      } else if (AppState.drawerOpen) {
        closeChatDrawer();
      }
    }
    // Ctrl+H opens chat history drawer
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'h') {
      e.preventDefault();
      if (AppState.drawerOpen) closeChatDrawer(); else openChatDrawer();
    }
  });

  // Kick off initialization
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBridge);
  } else {
    initBridge();
  }

})();
