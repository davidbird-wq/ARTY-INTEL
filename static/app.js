const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const trainForm = document.getElementById("train-form");
const qaForm = document.getElementById("qa-form");
const trainStatus = document.getElementById("train-status");
const kbList = document.getElementById("kb-list");
const refreshBtn = document.getElementById("refresh-kb");
const exportBtn = document.getElementById("export-kb");
const importBtn = document.getElementById("import-kb");
const importFile = document.getElementById("import-file");
const clearChatBtn = document.getElementById("clear-chat");

let sessionId = null;
let history = [];

function addMessage(role, content, tools = []) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
  if (tools.length) {
    const t = document.createElement("div");
    t.className = "tools";
    t.textContent = "Used: " + tools.join(", ");
    div.appendChild(t);
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Initial greeting
addMessage("assistant", "Hello! I'm a trainable AI agent. You can chat with me, ask me to use tools, or teach me new facts. Type \"help\" to see my abilities.");

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = userInput.value.trim();
  if (!text) return;

  addMessage("user", text);
  userInput.value = "";
  history.push({ role: "user", content: text });

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history, session_id: sessionId }),
    });
    const data = await res.json();
    sessionId = data.session_id;
    addMessage("assistant", data.reply, data.used_tools || []);
    history.push({ role: "assistant", content: data.reply });
  } catch (err) {
    addMessage("assistant", "Sorry, something went wrong connecting to the server.");
  }
});

trainForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fact = document.getElementById("fact-input").value.trim();
  if (!fact) return;

  try {
    const res = await fetch("/train", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fact }),
    });
    const data = await res.json();
    trainStatus.textContent = data.message + ` (total knowledge: ${data.knowledge_count})`;
    document.getElementById("fact-input").value = "";
    loadKnowledge();
  } catch (err) {
    trainStatus.textContent = "Training failed.";
  }
});

qaForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = document.getElementById("q-input").value.trim();
  const answer = document.getElementById("a-input").value.trim();
  if (!question || !answer) return;

  try {
    const res = await fetch("/train", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, answer }),
    });
    const data = await res.json();
    trainStatus.textContent = data.message + ` (total knowledge: ${data.knowledge_count})`;
    document.getElementById("q-input").value = "";
    document.getElementById("a-input").value = "";
    loadKnowledge();
  } catch (err) {
    trainStatus.textContent = "Training failed.";
  }
});

async function loadKnowledge() {
  try {
    const res = await fetch("/knowledge");
    const data = await res.json();
    if (!data.facts.length && !data.qa_pairs.length) {
      kbList.innerHTML = "<p>No knowledge yet. Teach me something!</p>";
      return;
    }
    let html = "";
    data.facts.slice(-8).reverse().forEach((f) => {
      html += `<div class="kb-item"><strong>Fact</strong>: ${escapeHtml(f.content)}</div>`;
    });
    data.qa_pairs.slice(-5).reverse().forEach((qa) => {
      html += `<div class="kb-item"><strong>Q</strong>: ${escapeHtml(qa.question)}<br/><strong>A</strong>: ${escapeHtml(qa.answer)}</div>`;
    });
    kbList.innerHTML = html;
  } catch {
    kbList.innerHTML = "Could not load knowledge.";
  }
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

refreshBtn.addEventListener("click", loadKnowledge);

async function exportTrainingData() {
  try {
    const res = await fetch("/knowledge");
    const data = await res.json();

    const exportPayload = {
      exported_at: new Date().toISOString(),
      version: 1,
      facts: data.facts || [],
      qa_pairs: data.qa_pairs || [],
      total_items: data.count || 0,
    };

    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `training-data-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    trainStatus.textContent = `Exported ${exportPayload.total_items} items`;
  } catch (err) {
    trainStatus.textContent = "Export failed.";
  }
}

exportBtn.addEventListener("click", exportTrainingData);

// Import training data
importBtn.addEventListener("click", () => importFile.click());

importFile.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  try {
    const text = await file.text();
    const data = JSON.parse(text);

    const res = await fetch("/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const result = await res.json();

    if (result.success) {
      trainStatus.textContent = result.message + ` (total: ${result.knowledge_count})`;
      loadKnowledge();
    } else {
      trainStatus.textContent = "Import failed.";
    }
  } catch (err) {
    trainStatus.textContent = "Invalid file or import error.";
  }

  importFile.value = ""; // reset so same file can be chosen again
});

// Clear chat
clearChatBtn.addEventListener("click", () => {
  messagesEl.innerHTML = "";
  history = [];
  sessionId = null;
  addMessage("assistant", "Chat cleared. Hello again! How can I help you?");
});

loadKnowledge();
