<template>
  <div class="chat-container">
    <header class="chat-header">
      <div class="header-title">
        <h2>Paper QA</h2>
      </div>
      
      <!-- PDF Yükleme Alanı -->
      <div class="upload-area">
        <label class="upload-btn" :class="{ 'btn-disabled': uploadLoading }">
          <input 
            type="file" 
            accept=".pdf" 
            @change="handleFileUpload" 
            :disabled="uploadLoading" 
            hidden 
          />
          {{ uploadLoading ? 'Makale İşleniyor...' : '📄 PDF Makale Yükle' }}
        </label>
        <span class="upload-status" v-if="uploadStatus">{{ uploadStatus }}</span>
      </div>
    </header>

    <div class="messages-box" ref="messagesContainer">
      <div 
        v-for="(msg, index) in messages" 
        :key="index" 
        :class="['message', msg.sender === 'user' ? 'user-message' : 'bot-message']"
      >
        <div class="bubble">
          {{ msg.text }}
        </div>
      </div>
      <div v-if="loading" class="message bot-message">
        <div class="bubble loading-bubble">Makale taranıyor ve yanıt hazırlanıyor...</div>
      </div>
    </div>

    <form @submit.prevent="sendMessage" class="input-area">
      <input 
        v-model="userInput" 
        type="text" 
        placeholder="Yüklediğiniz makale hakkında bir soru sorun..." 
        :disabled="loading || uploadLoading"
      />
      <button type="submit" :disabled="!userInput.trim() || loading || uploadLoading">
        Gönder
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const userInput = ref('')
const loading = ref(false)
const uploadLoading = ref(false)
const uploadStatus = ref('')
const messagesContainer = ref(null)

const messages = ref([
  { 
    sender: 'bot', 
    text: 'Sisteme hoş geldiniz. Lütfen analiz etmek istediğiniz PDF makalesini yukarıdan yükleyin.' 
  }
])

const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// PDF Yükleme Fonksiyonu
const handleFileUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return

  const formData = new FormData()
  formData.append('file', file)

  uploadLoading.value = true
  uploadStatus.value = ''
  
  try {
    const response = await fetch('http://127.0.0.1:8000/documents', {
      method: 'POST',
      body: formData // Form data kullanıldığında Content-Type otomatik ayarlanır
    })

    if (!response.ok) throw new Error('Yükleme başarısız')
    
    const data = await response.json()
    uploadStatus.value = `✅ "${data.dosya_adi}" başarıyla işlendi (${data.eklenen_parca_sayisi} parça).`
    messages.value.push({ sender: 'bot', text: `Makale sisteme yüklendi ve vektör veritabanına işlendi. Şimdi sorularınızı sorabilirsiniz.` })
    scrollToBottom()
  } catch (error) {
    uploadStatus.value = '❌ Yükleme sırasında bir hata oluştu.'
    console.error(error)
  } finally {
    uploadLoading.value = false
    event.target.value = '' // Aynı dosyayı tekrar seçebilmek için inputu temizle
  }
}

// Mesaj Gönderme Fonksiyonu
const sendMessage = async () => {
  const query = userInput.value.trim()
  if (!query || loading.value) return

  messages.value.push({ sender: 'user', text: query })
  userInput.value = ''
  loading.value = true
  scrollToBottom()

  try {
    const response = await fetch('http://127.0.0.1:8000/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: query })
    })

    if (!response.ok) throw new Error('Sunucu hatası')
    
    const data = await response.json()
    messages.value.push({ sender: 'bot', text: data.cevap || 'Cevap alınamadı.' })
  } catch (error) {
    messages.value.push({ 
      sender: 'bot', 
      text: 'Backend bağlantısı kurulamadı. FastAPI sunucusunun (8000 portu) çalıştığından emin olun.' 
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
}

body {
  background-color: #edf2f7;
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
}

.chat-container {
  width: 100%;
  max-width: 650px;
  height: 85vh;
  background: #f8fafc;
  border-radius: 16px;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  background-color: #3b828e;
  color: #ffffff;
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.header-title h2 {
  font-size: 1.15rem;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.upload-area {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.85rem;
}

.upload-btn {
  background-color: #fde68a;
  color: #451a03;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  transition: opacity 0.2s;
  display: inline-block;
}

.upload-btn:hover {
  opacity: 0.9;
}

.btn-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.upload-status {
  color: #e2e8f0;
  font-weight: 500;
}

.messages-box {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  display: flex;
  width: 100%;
}

.user-message {
  justify-content: flex-end;
}

.bot-message {
  justify-content: flex-start;
}

.bubble {
  max-width: 80%;
  padding: 12px 18px;
  border-radius: 14px;
  font-size: 0.95rem;
  line-height: 1.5;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.user-message .bubble {
  background-color: #fde68a;
  color: #451a03;
  border-bottom-right-radius: 2px;
}

.bot-message .bubble {
  background-color: #ffffff;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  border-bottom-left-radius: 2px;
}

.loading-bubble {
  font-style: italic;
  color: #64748b;
  background-color: #f1f5f9;
  border: 1px solid transparent;
}

.input-area {
  display: flex;
  gap: 12px;
  padding: 18px 24px;
  border-top: 1px solid #e2e8f0;
  background-color: #ffffff;
}

.input-area input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  outline: none;
  font-size: 0.95rem;
  background-color: #f8fafc;
  color: #1e293b;
  transition: border-color 0.2s;
}

.input-area input:focus {
  border-color: #3b828e;
}

.input-area button {
  padding: 12px 24px;
  background-color: #3b828e;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.95rem;
  transition: background-color 0.2s;
}

.input-area button:hover:not(:disabled) {
  background-color: #2f6974;
}

.input-area button:disabled {
  background-color: #cbd5e1;
  cursor: not-allowed;
}
</style>