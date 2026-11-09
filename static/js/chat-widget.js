/**
 * Cathea Studio — "Consult Us" AI Concierge
 * Minimalist Monochrome / Zero Roundness
 */

document.addEventListener('DOMContentLoaded', () => {
  const triggerBtn = document.getElementById('consultTriggerBtn');
  const drawer = document.getElementById('consultDrawer');
  const closeBtn = document.getElementById('consultCloseBtn');
  const form = document.getElementById('consultForm');
  const input = document.getElementById('consultInput');
  const messages = document.getElementById('consultMessages');
  const waDirectLink = document.getElementById('consultWaDirect');

  if (!triggerBtn || !drawer) return;

  const waNumber = drawer.dataset.waNumber || '6281234567890';
  let chatHistory = [];

  function toggleDrawer() {
    drawer.classList.toggle('open');
    if (drawer.classList.contains('open') && input) {
      input.focus();
    }
  }

  triggerBtn.addEventListener('click', toggleDrawer);
  if (closeBtn) closeBtn.addEventListener('click', toggleDrawer);

  function getWhatsAppUrl(note = '') {
    const text = note ? `Hello Cathea Studio, regarding: ${note}` : 'Hello Cathea Studio, I would like to consult about a wedding or prewedding project.';
    return `https://wa.me/${waNumber}?text=${encodeURIComponent(text)}`;
  }

  if (waDirectLink) {
    waDirectLink.href = getWhatsAppUrl();
  }

  function appendMsg(text, type = 'agent', isTransfer = false) {
    const bubble = document.createElement('div');
    bubble.className = `consult-bubble ${type}`;

    if (isTransfer) {
      bubble.className = 'consult-bubble transfer-card';
      const lastUser = chatHistory.filter(m => m.sender === 'user').pop()?.text || 'project consultation';
      bubble.innerHTML = `
        <p>Transfer ongoing consultation to our studio director:</p>
        <a href="${getWhatsAppUrl(lastUser)}" target="_blank" class="btn-transfer-wa">
          Continue on WhatsApp &rarr;
        </a>
      `;
    } else {
      bubble.innerHTML = text.replace(/\n/g, '<br>');
    }

    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
  }

  function showTyping() {
    const el = document.createElement('div');
    el.className = 'consult-bubble agent';
    el.id = 'consultTyping';
    el.innerHTML = '<span style="font-size: 0.75rem; letter-spacing: 0.1em; color: #888;">CONSULTING...</span>';
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  function removeTyping() {
    const el = document.getElementById('consultTyping');
    if (el) el.remove();
  }

  async function sendConsult(msg) {
    if (!msg.trim()) return;

    appendMsg(msg, 'user');
    chatHistory.push({ sender: 'user', text: msg });
    if (input) input.value = '';

    showTyping();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, history: chatHistory })
      });

      const data = await res.json();
      removeTyping();

      if (data.reply) {
        appendMsg(data.reply, 'agent');
        chatHistory.push({ sender: 'agent', text: data.reply });

        if (data.suggest_whatsapp) {
          appendMsg('', 'transfer', true);
        }
      }
    } catch (e) {
      removeTyping();
      appendMsg('Our creative assistant is momentarily offline. Please consult directly via WhatsApp.', 'agent');
      appendMsg('', 'transfer', true);
    }
  }

  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      sendConsult(input.value);
    });
  }
});
