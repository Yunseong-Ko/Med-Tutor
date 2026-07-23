"use strict";

/**
 * CpxVoice: AI 실전모드 음성 경계 (Web Speech API 기반).
 * - STT: 마이크로 말하면 텍스트로 변환 (Chrome/Edge/Safari 내장, ko-KR)
 * - TTS: 환자 답변을 소리로 읽어줌 (speechSynthesis)
 * 나중에 Whisper/ElevenLabs 같은 API로 교체할 때 이 파일만 바꾸면 된다.
 */
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  let recognition = null;
  let listening = false;
  let koVoice = null;

  function pickVoice() {
    if (!window.speechSynthesis) return;
    const voices = window.speechSynthesis.getVoices() || [];
    koVoice =
      voices.find((v) => v.lang && v.lang.replace("_", "-").startsWith("ko") && v.localService) ||
      voices.find((v) => v.lang && v.lang.replace("_", "-").startsWith("ko")) ||
      null;
  }

  if (window.speechSynthesis) {
    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;
  }

  function start(handlers) {
    const { onInterim, onFinal, onEnd, onError } = handlers || {};
    if (!SR || listening) return false;
    stopSpeaking();
    recognition = new SR();
    recognition.lang = "ko-KR";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    let finalText = "";
    recognition.onresult = (event) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      if (interim && onInterim) onInterim(interim);
    };
    recognition.onerror = (event) => {
      listening = false;
      if (onError) onError(event.error);
    };
    recognition.onend = () => {
      listening = false;
      if (finalText.trim() && onFinal) onFinal(finalText.trim());
      if (onEnd) onEnd();
    };

    try {
      recognition.start();
      listening = true;
      return true;
    } catch {
      listening = false;
      return false;
    }
  }

  function stop() {
    if (recognition && listening) {
      try {
        recognition.stop();
      } catch {
        listening = false;
      }
    }
  }

  function speak(text, opts = {}) {
    if (!window.speechSynthesis || !text) return;
    stopSpeaking();
    const utterance = new SpeechSynthesisUtterance(String(text));
    utterance.lang = "ko-KR";
    if (koVoice) utterance.voice = koVoice;
    utterance.rate = opts.rate || 1.05;
    utterance.pitch = opts.pitch || 1.0;
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeaking() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  window.CpxVoice = {
    sttSupported: Boolean(SR),
    ttsSupported: Boolean(window.speechSynthesis),
    isListening: () => listening,
    start,
    stop,
    speak,
    stopSpeaking
  };
})();
