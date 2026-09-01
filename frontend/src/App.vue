<template>
  <div class="app-container" :style="appStyles">
    <aside class="sidebar" ref="sidebarRef" :style="sidebarStyle">
      <div class="brand">
        <svg class="logo" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="10" y="8" width="34" height="46" rx="6" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.8"/>
          <path d="M18 20H36 M18 30H36 M18 40H26" stroke="currentColor" stroke-width="3" stroke-linecap="round" opacity="0.8"/>
          <circle cx="42" cy="42" r="16" fill="var(--sidebar-bg)" />
          <circle cx="42" cy="42" r="13" stroke="currentColor" stroke-width="3.5" />
          <path d="M51 51L59 59" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
          <path d="M42 34 Q42 42 50 42 Q42 42 42 50 Q42 42 34 42 Q42 42 42 34 Z" fill="currentColor"/>
          <path d="M54 6 Q54 14 62 14 Q54 14 54 22 Q54 14 46 14 Q54 14 54 6 Z" fill="currentColor"/>
        </svg>
        <h2>Makale Asistanı</h2>
      </div>
      <button @click="startNewChat" class="new-chat-btn"><span class="icon">+</span> Yeni Sohbet</button>
      <div class="history-section">
        <h3>Önceki Sohbetler</h3>
        <ul class="history-list">
          <li v-for="chat in chatHistory" :key="chat.id" @click="loadChat(chat)" :class="{ active: currentChatId === chat.id }">
            <div v-if="editingChatId === chat.id" class="edit-title-box" @click.stop>
              <input v-model="editTitleText" @keyup.enter="saveChatTitle(chat.id)" @keyup.esc="cancelEditing" ref="titleInputRef" type="text" class="edit-title-input" />
              <button class="action-btn save-btn" @click="saveChatTitle(chat.id)" title="Kaydet">✔</button>
              <button class="action-btn cancel-btn" @click="cancelEditing" title="İptal">✕</button>
            </div>
            <template v-else>
              <div class="history-item-content" @dblclick.stop="startEditing(chat)">
                <div v-if="chat.files?.length || chat.fileName" class="history-file-name" :title="(chat.files || [chat.fileName]).join(', ')">📄 {{ (chat.files || [chat.fileName]).join(', ') }}</div>
                <div class="history-title-row"><span v-if="chat.files?.length || chat.fileName" class="tree-branch">└</span><span class="chat-title-text" :title="`Yeniden adlandır: ${chat.title}`">{{ chat.title }}</span></div>
              </div>
              <div class="chat-actions">
                <button class="action-btn edit-btn" @click.stop="startEditing(chat)" title="Yeniden Adlandır">✎</button>
                <button class="action-btn delete-btn" @click.stop="deleteChat(chat.id)" title="Sil">✕</button>
              </div>
            </template>
          </li>
          <li v-if="chatHistory.length === 0" class="empty-history">Henüz sohbet yok</li>
        </ul>
      </div>
      <div class="theme-toggle-area" ref="themeToggleAreaRef">
        <div v-if="isThemeModalOpen" class="theme-popover" @mouseleave="hoverThemeId = null">
          <div class="popover-header"><span>🎨 Temalar</span><button class="popover-close" @click="isThemeModalOpen = false">✕</button></div>
          <div class="popover-scroll">
            <div class="theme-subgroup-title">Koyu Temalar</div>
            <div class="popover-list">
              <div v-for="t in darkThemes" :key="t.id" :class="['compact-theme-card',{active:activeThemeId===t.id}]" @mouseenter="hoverThemeId=t.id" @click="setActiveTheme(t.id)">
                <div class="color-palette-dots"><span class="palette-dot" :style="{backgroundColor:t.vars['--primary']}"></span><span class="palette-dot" :style="{backgroundColor:t.vars['--bg-main']}"></span><span class="palette-dot" :style="{backgroundColor:t.vars['--sidebar-bg']}"></span></div>
                <span class="theme-label">{{ t.icon }} {{ t.name }}</span><span v-if="activeThemeId===t.id" class="active-check">✓</span>
              </div>
            </div>
            <div class="theme-subgroup-title" style="margin-top:10px;">Açık Temalar</div>
            <div class="popover-list">
              <div v-for="t in lightThemes" :key="t.id" :class="['compact-theme-card',{active:activeThemeId===t.id}]" @mouseenter="hoverThemeId=t.id" @click="setActiveTheme(t.id)">
                <div class="color-palette-dots"><span class="palette-dot" :style="{backgroundColor:t.vars['--primary']}"></span><span class="palette-dot" :style="{backgroundColor:t.vars['--bg-main']}"></span><span class="palette-dot" :style="{backgroundColor:t.vars['--sidebar-bg']}"></span></div>
                <span class="theme-label">{{ t.icon }} {{ t.name }}</span><span v-if="activeThemeId===t.id" class="active-check">✓</span>
              </div>
            </div>
          </div>
        </div>
        <button class="theme-toggle-btn" @click="isThemeModalOpen=!isThemeModalOpen">🎨 Tema Seçimi</button>
      </div>
    </aside>
    <div class="sidebar-resizer" :class="{'is-resizing':isSidebarResizing}" @pointerdown.prevent="startSidebarResize" title="Sohbet geçmişi menüsünün genişliğini ayarla" aria-label="Sohbet geçmişi menüsünün genişliğini ayarla"><div class="sidebar-resizer-handle"></div></div>
    <div class="content-wrapper">
      <section v-if="isPdfVisible && computedPdfUrl" :key="'pdf-sec-'+pdfViewerKey" class="pdf-viewer-panel" :style="{width:pdfWidth+'%'}">
        <div class="pdf-header">
          <span class="pdf-title">📄 {{ activeFileName }}</span>
          <div class="pdf-search-bar" v-if="activeFileName">
            <span class="search-icon">🔍</span>
            <input ref="pdfSearchInputRef" v-model="pdfSearchQuery" @keyup.enter.prevent="executePdfSearch" @keydown.esc.prevent="clearSearch" placeholder="Makalede ara" :disabled="isPdfSearching" autocomplete="off" />
            <div v-if="isPdfSearching" class="search-spinner"></div>
            <div v-else-if="pdfSearchMatches && pdfSearchMatches.length>0" class="search-nav">
              <span class="match-count">{{ currentMatchIndex+1 }} / {{ pdfSearchMatches.length }}</span>
              <button @click="prevMatch" title="Önceki">←</button><button @click="nextMatch" title="Sonraki">→</button><button @click="clearSearch" class="clear-search-btn" title="Aramayı Temizle">✕</button>
            </div>
            <div v-else-if="pdfSearchMatches && pdfSearchMatches.length===0" class="search-nav"><span class="match-count no-result">Sonuç yok</span><button @click="clearSearch" class="clear-search-btn">✕</button></div>
          </div>
          <button class="close-pdf-btn" @click="closePdf" title="Önizlemeyi Kapat">✕</button>
        </div>
        <iframe :key="'iframe-'+pdfViewerKey" :src="computedPdfUrl" class="pdf-frame" :style="{pointerEvents:isResizing?'none':'auto'}" title="PDF Önizleme"></iframe>
      </section>
      <div v-if="isPdfVisible && computedPdfUrl" class="resizer" @mousedown="startResize" :class="{'is-resizing':isResizing}"><div class="resizer-handle"></div></div>
      <main class="main-chat">
        <div class="messages-container" ref="messagesContainer">
          <div v-if="messages.length<=1 && !isUploading" class="welcome-screen">
            <div class="welcome-icon">📚🤖</div><h2>Hangi makaleyi analiz etmek istersiniz?</h2><p>Soru sormaya başlamadan önce analiz edilecek PDF makalesini yükleyin.</p>
            <label class="welcome-upload-btn"><input type="file" accept=".pdf" @change="handleFileUpload" multiple hidden />📄 PDF Makale Seç ve Yükle</label>
          </div>
          <div v-if="isUploading" class="message-row bot-row">
            <div class="avatar bot-avatar">🤖</div>
            <div class="chat-bubble bot-bubble upload-progress-bubble">
              <div class="upload-header">📄 <strong>{{ uploadFileName }}</strong><span class="upload-percent" :style="{color:'var(--primary)'}">%{{ Math.round(uploadProgress) }}</span></div>
              <div class="progress-bar-bg"><div class="progress-bar-fill" :style="{width:uploadProgress+'%'}"></div></div>
              <ul class="upload-steps"><li v-for="step in uploadSteps" :key="step.id" :class="{done:step.done,active:step.active}"><span class="step-icon">{{ step.done?'✓':(step.active?'⟳':'○') }}</span>{{ step.text }}</li></ul>
            </div>
          </div>
          <div v-for="(msg,index) in messages" :key="index" :class="['message-row',msg.sender==='user'?'user-row':'bot-row']">
            <div v-if="msg.sender==='bot'" class="avatar bot-avatar">🤖</div>
            <div v-if="msg.sender==='bot' && msg.out_of_context && !msg.upload_error" class="chat-bubble out-of-context-card"><div class="ooc-header">⚠️ Makalede bu bilgi bulunamadı.</div><div class="ooc-body">Bu asistan yalnızca yüklenen makalenin içeriğine dayanarak cevap verir. Sorunuzun cevabı yüklenen makalede bulunmadığı için dışarıdan bilgi kullanılmadı.</div></div>
            <div v-else :class="['chat-bubble',msg.sender==='user'?'user-bubble':'bot-bubble']">
              <details v-if="msg.thoughts" class="thought-container"><summary class="thought-summary">🧠 Düşünce sürecini incele</summary><div class="thought-content">{{ msg.thoughts }}</div></details>
              <div class="markdown-body" v-html="renderMarkdown(msg.text)"></div>
              <div v-if="msg.sources && msg.sources.length>0" class="source-buttons">
                <div class="source-title">📚 Kaynaklar</div>
                <div class="source-list"><button v-for="page in msg.sources" :key="page" :class="['source-btn',{active:activeHighlightFile===msg.highlighted_file && activePdfPage===page}]" @click="toggleSourceHighlight(msg,page)" title="Bu sayfadaki kaynak cümleleri gör">Sayfa {{ page }}</button></div>
              </div>
              <div v-if="index!==0" :class="['bubble-actions',msg.sender==='user'?'user-actions':'']"><button class="copy-btn" @click="copyToClipboard(msg.text,index)">{{ copiedIndex===index?'✔ Kopyalandı':'📋 Kopyala' }}</button></div>
            </div>
          </div>
          <div v-if="isThinking" class="message-row bot-row"><div class="avatar bot-avatar">🤖</div><div class="chat-bubble bot-bubble live-thinking"><span class="live-pulse">💭</span>{{ currentLiveThoughts || 'Makale inceleniyor...' }}</div></div>
        </div>
        <div class="input-container">
          <div v-if="activeFiles.length > 0" style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; max-width: 850px; width: 100%;">
  <span v-for="file in activeFiles" :key="file" class="active-file-tag" :class="{selected:file===activeFileName}" style="margin-bottom:0;width:auto;cursor:pointer;" @click="selectActivePdf(file)">
    📄 <strong>{{ file }}</strong>
    <button @click.stop="activeFiles = activeFiles.filter(f => f !== file)" style="background:transparent;border:none;color:#ef4444;cursor:pointer;margin-left:8px;font-weight:bold;" title="Listeden Çıkar">✕</button>
  </span>
  <button v-if="!isPdfVisible" @click="reopenPdf" class="reopen-pdf-btn">PDF'i Aç</button>
</div>
          <form @submit.prevent="sendMessage" class="input-box">
            <select v-model="selectedModel" class="model-select" :disabled="isThinking || isUploading" title="Yapay zeka modelini seçin">
              <option v-for="model in availableModels" :key="model.id" :value="model.id">{{ model.name }}</option>
            </select>
            <label class="attach-btn" :class="{disabled:isUploading}" title="PDF Makale Yükle"><input type="file" accept=".pdf" @change="handleFileUpload" :disabled="isUploading" multiple hidden /><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.48-8.48"/></svg></label>
            <input v-model="userInput" type="text" placeholder="Makale hakkında soru sorun..." :disabled="isThinking || isUploading" />
            <button v-if="!isThinking" type="submit" :disabled="!userInput.trim() || isUploading" class="send-btn">Gönder</button><button v-else type="button" @click="stopResponse" class="stop-btn icon-only" title="Durdur">■</button>
          </form>
          <div class="disclaimer">Yapay zeka hata yapabilir. Lütfen teknik bilgileri orijinal makaleden teyit ediniz.</div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const API_BASE='http://127.0.0.1:8000'
const STORAGE_KEY_HISTORY='makale_asistani_history'
const STORAGE_KEY_THEME='makale_theme_v2'
marked.setOptions({breaks:true,gfm:true})

const renderMarkdown=(text)=>{
  if(!text)return ''
  const cleanText=String(text).replace(/[\uFFFD\u0000]/g,'')
  const renderMath=(content,isDisplayMode)=>{
    try{return katex.renderToString(content.trim(),{displayMode:isDisplayMode,throwOnError:false,errorColor:'var(--text-muted)'})}catch{return isDisplayMode?`$$${content}$$`:`$${content}$`}
  }
  const formatted=cleanText.replace(/\$\$([\s\S]*?)\$\$/g,(_,eq)=>renderMath(eq,true)).replace(/\$([^\$\n]+?)\$/g,(_,eq)=>renderMath(eq,false))
  return marked.parse(formatted)
}

const themes=[
  {id:'ocean',name:'Okyanus',icon:'🌊',type:'dark',vars:{'--primary':'#2563EB','--bg-main':'#0B1120','--sidebar-bg':'#0F172A','--chat-bubble-bot':'#1E293B','--text-main':'#F8FAFC','--text-muted':'#94A3B8','--border-color':'#334155','--input-bg':'#0F172A','--hover-bg':'#1E293B'}},
  {id:'night-purple',name:'Gece Moru',icon:'🌌',type:'dark',vars:{'--primary':'#8B5CF6','--bg-main':'#11101C','--sidebar-bg':'#171427','--chat-bubble-bot':'#242036','--text-main':'#F8FAFC','--text-muted':'#A7A5B4','--border-color':'#3B3454','--input-bg':'#171427','--hover-bg':'#242036'}},
  {id:'emerald',name:'Zümrüt',icon:'🌿',type:'dark',vars:{'--primary':'#10B981','--bg-main':'#071713','--sidebar-bg':'#0A231D','--chat-bubble-bot':'#133129','--text-main':'#F8FAFC','--text-muted':'#9CA3AF','--border-color':'#224E41','--input-bg':'#0A231D','--hover-bg':'#133129'}},
  {id:'academic',name:'Akademik',icon:'☁️',type:'light',vars:{'--primary':'#2563EB','--bg-main':'#F8FAFC','--sidebar-bg':'#F1F5F9','--chat-bubble-bot':'#FFFFFF','--text-main':'#0F172A','--text-muted':'#64748B','--border-color':'#E2E8F0','--input-bg':'#FFFFFF','--hover-bg':'#E2E8F0'}},
  {id:'soft-purple',name:'Soft Purple',icon:'🌸',type:'light',vars:{'--primary':'#A855F7','--bg-main':'#FAF5FF','--sidebar-bg':'#F3E8FF','--chat-bubble-bot':'#FFFFFF','--text-main':'#3B0764','--text-muted':'#6B7280','--border-color':'#E9D5FF','--input-bg':'#FFFFFF','--hover-bg':'#E9D5FF'}},
  {id:'mint',name:'Mint',icon:'🌱',type:'light',vars:{'--primary':'#059669','--bg-main':'#ECFDF5','--sidebar-bg':'#D1FAE5','--chat-bubble-bot':'#FFFFFF','--text-main':'#064E3B','--text-muted':'#4B5563','--border-color':'#A7F3D0','--input-bg':'#FFFFFF','--hover-bg':'#A7F3D0'}}
]
const darkThemes=themes.filter(t=>t.type==='dark')
const lightThemes=themes.filter(t=>t.type==='light')
const activeThemeId=ref('ocean')
const hoverThemeId=ref(null)
const isThemeModalOpen=ref(false)
const themeToggleAreaRef=ref(null)
const currentThemeObj=computed(()=>themes.find(t=>t.id===(hoverThemeId.value||activeThemeId.value))||themes[0])
const appStyles=computed(()=>currentThemeObj.value.vars)
const setActiveTheme=(id)=>{activeThemeId.value=id;hoverThemeId.value=null;localStorage.setItem(STORAGE_KEY_THEME,id);isThemeModalOpen.value=false}

const availableModels = [
  { id: 'local', name: 'Yerel Qwen 7B' },
  { id: 'openrouter/free', name: 'Ücretsiz Bulut (OpenRouter)' }
]
const selectedModel = ref('local')
const userInput=ref('')
const isThinking=ref(false)
const copiedIndex=ref(null)
const messagesContainer=ref(null)
const titleInputRef=ref(null)
const sidebarRef=ref(null)
const sidebarWidth=ref(280)
const isSidebarResizing=ref(false)
const activeFiles = ref([])
const activeFileName = computed(() => activeFiles.value.length > 0 ? activeFiles.value[activeFiles.value.length - 1] : '')
const pdfViewerKey=ref(1)
const isPdfVisible=ref(false)
const currentLiveThoughts=ref('')
const abortController=ref(null)
const chatHistory=ref([])
const currentChatId=ref(Date.now())
const messages=ref([])
const editingChatId=ref(null)
const editTitleText=ref('')
const isUploading=ref(false)
const uploadFileName=ref('')
const uploadProgress=ref(0)
const targetProgress=ref(0)
const uploadSteps=ref([{id:1,text:'PDF yüklendi',done:false,active:false},{id:2,text:'Metin çıkarıldı',done:false,active:false},{id:3,text:'Metin parçalara ayrıldı',done:false,active:false},{id:4,text:'Embedding oluşturuldu',done:false,active:false},{id:5,text:"Qdrant'a kaydedildi (Hazır)",done:false,active:false}])
let progressLoop=null
const activeHighlightFile=ref(null)
const activeSearchFile=ref(null)
const pdfSearchInputRef=ref(null)
const pdfSearchQuery=ref('')
const isPdfSearching=ref(false)
const pdfSearchMatches=ref(null)
const currentMatchIndex=ref(0)
const activePdfPage=ref(1)
const pdfWidth=ref(50)
const isResizing=ref(false)
let pdfOpenGeneration=0

const sidebarStyle=computed(()=>({width:sidebarWidth.value+'px',flexBasis:sidebarWidth.value+'px'}))
const computedPdfUrl=computed(()=>{
  if(!activeFileName.value)return ''
  let fileToLoad=activeFileName.value
  if(activeSearchFile.value)fileToLoad=activeSearchFile.value
  else if(activeHighlightFile.value)fileToLoad=activeHighlightFile.value
  return `${API_BASE}/pdf/${encodeURIComponent(fileToLoad)}?v=${pdfViewerKey.value}#page=${activePdfPage.value}`
})

const handleGlobalKeydown=async(e)=>{
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='f'&&activeFileName.value){e.preventDefault();if(!isPdfVisible.value)await refreshPdfViewer();nextTick(()=>pdfSearchInputRef.value?.focus())}
}

onMounted(()=>{
  const savedTheme=localStorage.getItem(STORAGE_KEY_THEME)
  if(savedTheme)activeThemeId.value=savedTheme
  const saved=localStorage.getItem(STORAGE_KEY_HISTORY)
  if(saved){try{chatHistory.value=JSON.parse(saved)}catch{chatHistory.value=[]}}
  startNewChat()
  document.addEventListener('click',handleClickOutsideTheme)
  window.addEventListener('keydown',handleGlobalKeydown)
})

onUnmounted(()=>{
  window.removeEventListener('mousemove',handleResize);window.removeEventListener('mouseup',stopResize);window.removeEventListener('pointermove',handleSidebarResize);window.removeEventListener('pointerup',stopSidebarResize);window.removeEventListener('pointercancel',stopSidebarResize);document.removeEventListener('click',handleClickOutsideTheme);window.removeEventListener('keydown',handleGlobalKeydown);clearInterval(progressLoop)
})

const handleClickOutsideTheme=(e)=>{if(themeToggleAreaRef.value&&!themeToggleAreaRef.value.contains(e.target)){isThemeModalOpen.value=false;hoverThemeId.value=null}}

const toggleSourceHighlight=async(msg,page)=>{
  if(activeHighlightFile.value===msg.highlighted_file&&activePdfPage.value===page){activeHighlightFile.value=null;activeSearchFile.value=null}else{activeSearchFile.value=null;activeHighlightFile.value=msg.highlighted_file;activePdfPage.value=page}
  await refreshPdfViewer()
}

const executePdfSearch=async()=>{
  const query=pdfSearchQuery.value.trim()
  if(!query||!activeFileName.value||isPdfSearching.value)return
  isPdfSearching.value=true
  try{
    const currentPrimary=currentThemeObj.value.vars['--primary']
    const response=await fetch(`${API_BASE}/pdf_search_advanced`,{method:'POST',headers:{'Content-Type':'application/json','Cache-Control':'no-cache'},cache:'no-store',body:JSON.stringify({question:query,dosya_adi:activeFileName.value,theme_color:currentPrimary})})
    if(!response.ok){const errorText=await response.text();let detail=errorText;try{const data=JSON.parse(errorText);detail=data.detail||data.error||errorText}catch{}throw new Error(`Backend ${response.status}: ${detail}`)}
    const data=await response.json()
    if(data.success&&data.matches?.length){activeSearchFile.value=data.search_file;pdfSearchMatches.value=data.matches;currentMatchIndex.value=0;activePdfPage.value=data.matches[0];activeHighlightFile.value=null;await refreshPdfViewer()}else{activeSearchFile.value=null;pdfSearchMatches.value=[]}
  }catch(error){console.error('Arama hatası:',error)}finally{isPdfSearching.value=false}
}

const nextMatch=async()=>{if(pdfSearchMatches.value&&currentMatchIndex.value<pdfSearchMatches.value.length-1){currentMatchIndex.value++;activePdfPage.value=pdfSearchMatches.value[currentMatchIndex.value];await refreshPdfViewer()}}
const prevMatch=async()=>{if(pdfSearchMatches.value&&currentMatchIndex.value>0){currentMatchIndex.value--;activePdfPage.value=pdfSearchMatches.value[currentMatchIndex.value];await refreshPdfViewer()}}
const clearSearch=async(reloadPdf=true)=>{pdfSearchQuery.value='';pdfSearchMatches.value=null;activeSearchFile.value=null;if(reloadPdf&&activeFileName.value)await refreshPdfViewer()}

const startResize=(e)=>{e.preventDefault();isResizing.value=true;document.body.style.cursor='col-resize';window.addEventListener('mousemove',handleResize);window.addEventListener('mouseup',stopResize)}
const handleResize=(e)=>{if(!isResizing.value)return;const sidebarCurrentWidth=sidebarRef.value?sidebarRef.value.offsetWidth:280;const containerWidth=window.innerWidth-sidebarCurrentWidth;let newWidth=((e.clientX-sidebarCurrentWidth)/containerWidth)*100;if(newWidth<20)newWidth=20;if(newWidth>80)newWidth=80;pdfWidth.value=newWidth}
const stopResize=()=>{if(!isResizing.value)return;isResizing.value=false;document.body.style.cursor='';window.removeEventListener('mousemove',handleResize);window.removeEventListener('mouseup',stopResize)}
const startSidebarResize=()=>{isSidebarResizing.value=true;document.body.style.cursor='col-resize';window.addEventListener('pointermove',handleSidebarResize);window.addEventListener('pointerup',stopSidebarResize);window.addEventListener('pointercancel',stopSidebarResize)}
const handleSidebarResize=(event)=>{if(!isSidebarResizing.value)return;sidebarWidth.value=Math.min(440,Math.max(210,event.clientX))}
const stopSidebarResize=()=>{if(!isSidebarResizing.value)return;isSidebarResizing.value=false;document.body.style.cursor='';window.removeEventListener('pointermove',handleSidebarResize);window.removeEventListener('pointerup',stopSidebarResize);window.removeEventListener('pointercancel',stopSidebarResize)}
const syncHistory=()=>localStorage.setItem(STORAGE_KEY_HISTORY,JSON.stringify(chatHistory.value))

const startNewChat=()=>{currentChatId.value=Date.now();activeFiles.value = []; closePdf();editingChatId.value=null;editTitleText.value='';activePdfPage.value=1;activeHighlightFile.value=null;activeSearchFile.value=null;messages.value=[{sender:'bot',text:'Yeni bir oturum açıldı. PDF makalenizi yükleyerek başlayabilirsiniz.'}]}

const loadChat=async(chat)=>{currentChatId.value=chat.id;messages.value=chat.messages||[];activeFiles.value = chat.files ? chat.files : (chat.fileName ? [chat.fileName] : []);activePdfPage.value=1;activeHighlightFile.value=null;activeSearchFile.value=null;await clearSearch(false);editingChatId.value=null;if(activeFileName.value)await refreshPdfViewer();else closePdf()}
const deleteChat=(chatId)=>{chatHistory.value=chatHistory.value.filter(chat=>chat.id!==chatId);syncHistory();if(currentChatId.value===chatId)startNewChat()}

const saveCurrentChat=()=>{
  const index=chatHistory.value.findIndex(chat=>chat.id===currentChatId.value)
  const firstUserMessage=messages.value.find(m=>m.sender==='user')
  let title='Yeni Oturum'
  let customTitle=false
  if(index!==-1){customTitle=chatHistory.value[index].customTitle||false;if(customTitle)title=chatHistory.value[index].title;else if(firstUserMessage)title=firstUserMessage.text.substring(0,22)+(firstUserMessage.text.length>22?'...':'')}else if(firstUserMessage)title=firstUserMessage.text.substring(0,22)+(firstUserMessage.text.length>22?'...':'')
  const chatData={id:currentChatId.value,title,customTitle,messages:messages.value,files: activeFiles.value}
  if(index!==-1)chatHistory.value[index]=chatData;else chatHistory.value.unshift(chatData)
  syncHistory()
}

const startEditing=async(chat)=>{editingChatId.value=chat.id;editTitleText.value=chat.title;await nextTick();if(titleInputRef.value){const input=Array.isArray(titleInputRef.value)?titleInputRef.value[0]:titleInputRef.value;input?.focus()}}
const saveChatTitle=(chatId)=>{const chat=chatHistory.value.find(c=>c.id===chatId);if(chat&&editTitleText.value.trim()){chat.title=editTitleText.value.trim();chat.customTitle=true;syncHistory()}editingChatId.value=null}
const cancelEditing=()=>{editingChatId.value=null;editTitleText.value=''}
const scrollToBottom=async()=>{await nextTick();if(messagesContainer.value)messagesContainer.value.scrollTop=messagesContainer.value.scrollHeight}
const copyToClipboard=async(text,index)=>{try{await navigator.clipboard.writeText(String(text||''));copiedIndex.value=index;setTimeout(()=>copiedIndex.value=null,2000)}catch(error){console.error('Kopyalama hatası:',error)}}

/* PDF kilitlenmesini önleyen mekanizma */
const closePdf=()=>{pdfOpenGeneration++;isPdfVisible.value=false}
const refreshPdfViewer=async()=>{
  if(!activeFileName.value)return
  const requestId=++pdfOpenGeneration
  isPdfVisible.value=false
  await nextTick()
  if(requestId!==pdfOpenGeneration||!activeFileName.value)return
  pdfViewerKey.value++
  isPdfVisible.value=true
  await nextTick()
}
const reopenPdf=()=>refreshPdfViewer()
const selectActivePdf=async(file)=>{
  if(!activeFiles.value.includes(file))return
  activeFiles.value=[...activeFiles.value.filter(f=>f!==file),file]
  activePdfPage.value=1
  activeHighlightFile.value=null
  activeSearchFile.value=null
  pdfSearchQuery.value=''
  pdfSearchMatches.value=null
  await refreshPdfViewer()
}

const startProgressTicker=()=>{clearInterval(progressLoop);progressLoop=setInterval(()=>{if(uploadProgress.value<targetProgress.value)uploadProgress.value++},30)}

const setUploadStep=(stepNumber)=>{uploadSteps.value.forEach((step,index)=>{if(index+1<stepNumber){step.done=true;step.active=false}else if(index+1===stepNumber){step.done=false;step.active=true}else{step.done=false;step.active=false}})}

const handleFileUpload = async (event) => {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  for (let i = 0; i < files.length; i++) {
    const file = files[i];

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      messages.value.push({ sender: 'bot', text: `❌ **${file.name}** işlenirken hata: ${error.message}`, out_of_context: false, upload_error: true });
      continue;
    }

    isUploading.value = true;
    uploadFileName.value = file.name;
    uploadProgress.value = 0;
    targetProgress.value = 0;
    uploadSteps.value.forEach(step => { step.done = false; step.active = false });
    startProgressTicker();
    setUploadStep(1);
    await scrollToBottom();

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/documents_stream`, { method: 'POST', body: formData, cache: 'no-store' });

      if (!response.ok) {
        const errorText = await response.text();
        let detail = errorText;
        try {
          const errorData = JSON.parse(errorText);
          detail = errorData.detail || errorData.error || errorText;
        } catch {}
        throw new Error(`Backend ${response.status}: ${detail}`);
      }

      if (!response.body) throw new Error('Backend veri akışı başlatamadı.');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let uploadCompleted = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let payload;
          try { payload = JSON.parse(line.slice(6)); } catch { continue; }

          if (payload.error) throw new Error(payload.error);
          if (typeof payload.percent === 'number') targetProgress.value = payload.percent;
          if (payload.step) setUploadStep(payload.step);

          if (payload.done && !uploadCompleted) {
            uploadCompleted = true;
            targetProgress.value = 100;
            uploadSteps.value.forEach(step => { step.done = true; step.active = false });
            clearInterval(progressLoop);
            uploadProgress.value = 100;

            if (!activeFiles.value.includes(payload.dosya_adi)) activeFiles.value.push(payload.dosya_adi);

            activePdfPage.value = 1;
            activeHighlightFile.value = null;
            activeSearchFile.value = null;
            await clearSearch(false);
            await refreshPdfViewer();

            messages.value.push({
              sender: 'bot',
              text: `✅ **${payload.dosya_adi}** başarıyla ${payload.cached ? 'mevcut indeks kullanılarak ' : ''}hazırlandı.\n\n📚 **${payload.eklenen_parca_sayisi}** parça indeksli.\n\nArtık makale hakkında soru sorabilirsiniz.`,
              out_of_context: false
            });
            saveCurrentChat();
            await scrollToBottom();
          }
        }
      }
    } catch (error) {
      clearInterval(progressLoop);
      messages.value.push({ sender: 'bot', text: `❌ **${file.name}** işlenirken hata: ${error.message}`, out_of_context: true });
      await scrollToBottom();
    }
  }

  isUploading.value = false;
  event.target.value = '';
};

const stopResponse=()=>{if(abortController.value)abortController.value.abort();abortController.value=null;isThinking.value=false;currentLiveThoughts.value=''}

const sendMessage=async()=>{
  const query=userInput.value.trim()
  if(!query||isThinking.value)return
  if(activeFiles.value.length === 0){messages.value.push({sender:'user',text:query});messages.value.push({sender:'bot',text:'❌ Önce analiz etmek istediğiniz PDF makalesini yükleyin.',out_of_context:true});userInput.value='';await scrollToBottom();return}
  messages.value.push({sender:'user',text:query});userInput.value='';isThinking.value=true;currentLiveThoughts.value='Makale taranıyor...';saveCurrentChat();await scrollToBottom()
  if(abortController.value)abortController.value.abort()
  abortController.value=new AbortController()
  try{
    const currentPrimary=currentThemeObj.value.vars['--primary']
    const response=await fetch(`${API_BASE}/ask`,{method:'POST',headers:{'Content-Type':'application/json','Cache-Control':'no-cache'},cache:'no-store',body:JSON.stringify({question:query,dosya_adlari:activeFiles.value,theme_color:currentPrimary,model:selectedModel.value}),signal:abortController.value.signal})
    currentLiveThoughts.value='Yanıt hazırlanıyor...'
    if(!response.ok){const rawError=await response.text();let detail=rawError;try{const errorData=JSON.parse(rawError);detail=errorData.detail||errorData.error||rawError}catch{}throw new Error(`Backend ${response.status}: ${detail}`)}
    const rawText=await response.text()
    if(!rawText.trim())throw new Error('Backend boş cevap döndürdü.')
    let answer='';let sources=[];let highlighted_file=null;let out_of_context=false
    try{const data=JSON.parse(rawText);answer=data.answer||data.response||data.text||'';sources=data.sources||[];highlighted_file=data.highlighted_file||null;out_of_context=Boolean(data.out_of_context)}catch{answer=rawText.trim()}
    if(!answer||answer==='null'||answer==='undefined')answer='❌ Modelden geçerli bir yanıt alınamadı.'
    messages.value.push({sender:'bot',text:answer,thoughts:'',sources,highlighted_file,out_of_context});currentLiveThoughts.value='';saveCurrentChat();await scrollToBottom()
  }catch(error){
    if(error.name==='AbortError')messages.value.push({sender:'bot',text:'⏹ Yanıt üretimi durduruldu.',out_of_context:false})
    else messages.value.push({sender:'bot',text:`❌ Sistem bağlantı hatası.\n\n**Hata:** ${error.message}`,out_of_context:false})
  }finally{isThinking.value=false;currentLiveThoughts.value='';abortController.value=null;await scrollToBottom()}
}
</script>

<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,sans-serif}
html,body{height:100%;width:100%;overflow:hidden}
.app-container{display:flex;height:100vh;width:100vw;background-color:var(--bg-main);color:var(--text-main);transition:background-color .4s ease,color .4s ease}
.sidebar,.content-wrapper,.pdf-header,.input-container,.chat-bubble,.history-list li,.action-btn,.stop-btn,.send-btn,.pdf-search-bar{transition:background-color .4s ease,border-color .4s ease,color .4s ease}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border-color);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:var(--text-muted)}
.sidebar{width:280px;background-color:var(--sidebar-bg);border-right:1px solid var(--border-color);display:flex;flex-direction:column;padding:24px 16px;flex-shrink:0;z-index:10;min-width:210px;max-width:440px}
.sidebar-resizer{width:8px;flex:0 0 8px;background-color:var(--border-color);cursor:col-resize;display:flex;align-items:center;justify-content:center;z-index:20;touch-action:none}
.sidebar-resizer:hover,.sidebar-resizer.is-resizing{background-color:var(--primary)}
.sidebar-resizer-handle{width:2px;height:32px;border-radius:2px;background-color:rgba(128,128,128,.65)}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:24px;color:var(--text-main)}
.logo{width:44px;height:44px;color:var(--primary);filter:drop-shadow(0 0 6px var(--primary))}
.brand h2{font-size:1.3rem;font-weight:600}
.new-chat-btn{background:transparent;color:var(--text-main);border:1px solid var(--border-color);padding:10px;border-radius:8px;cursor:pointer;font-weight:500;display:flex;align-items:center;gap:8px;margin-bottom:20px}
.new-chat-btn:hover{background:var(--hover-bg)}
.history-section{flex:1;overflow-y:auto;border-top:1px solid var(--border-color);padding-top:16px}
.history-section h3{font-size:.75rem;color:var(--text-muted);margin-bottom:12px;text-transform:uppercase}
.history-list{list-style:none}
.history-list li{display:flex;align-items:flex-start;justify-content:space-between;padding:10px;border-radius:6px;cursor:pointer;font-size:.88rem;color:var(--text-main);margin-bottom:6px}
.history-list li:hover{background:var(--hover-bg)}
.history-list li.active{background:var(--hover-bg);border-left:3px solid var(--primary);font-weight:600}
.history-item-content{flex:1;display:flex;flex-direction:column;gap:4px;overflow:hidden}
.history-file-name{font-size:.75rem;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500}
.history-title-row{display:flex;align-items:center;gap:6px}
.tree-branch{color:var(--text-muted);font-size:.85rem}
.chat-title-text{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
.chat-actions{display:flex;gap:4px;opacity:0;margin-top:2px}
.history-list li:hover .chat-actions{opacity:1}
.action-btn{background:transparent;border:none;color:var(--text-muted);cursor:pointer;padding:2px 6px;border-radius:4px}
.action-btn:hover{color:var(--primary)}
.edit-title-box{display:flex;align-items:center;gap:4px;width:100%}
.edit-title-input{flex:1;background:var(--input-bg);border:1px solid var(--primary);color:var(--text-main);padding:3px 6px;font-size:.8rem;border-radius:4px}
.theme-toggle-area{padding-top:12px;border-top:1px solid var(--border-color);position:relative}
.theme-toggle-btn{width:100%;padding:10px;background:var(--input-bg);border:1px solid var(--border-color);color:var(--text-main);border-radius:8px;cursor:pointer;font-weight:500}
.theme-toggle-btn:hover{background:var(--hover-bg)}
.theme-popover{position:absolute;bottom:105%;left:0;width:100%;background:var(--sidebar-bg);border:1px solid var(--border-color);border-radius:12px;padding:12px;box-shadow:0 10px 25px rgba(0,0,0,.3);z-index:50}
.popover-header{display:flex;justify-content:space-between;align-items:center;font-size:.85rem;font-weight:600;color:var(--text-main);margin-bottom:8px;border-bottom:1px solid var(--border-color);padding-bottom:6px}
.popover-close{background:transparent;border:none;color:var(--text-muted);cursor:pointer}
.popover-close:hover{color:#ef4444}
.popover-scroll{max-height:250px;overflow-y:auto}
.theme-subgroup-title{font-size:.7rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px}
.popover-list{display:flex;flex-direction:column;gap:4px}
.compact-theme-card{display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-radius:6px;border:1px solid transparent;cursor:pointer;background:var(--input-bg)}
.compact-theme-card:hover,.compact-theme-card.active{border-color:var(--primary);background:var(--hover-bg)}
.color-palette-dots{display:flex;gap:3px;align-items:center}
.palette-dot{width:8px;height:8px;border-radius:50%;border:1px solid rgba(0,0,0,.1)}
.theme-label{font-size:.8rem;color:var(--text-main);flex:1;margin-left:8px}
.active-check{color:var(--primary);font-size:.85rem}
.content-wrapper{flex:1;display:flex;height:100%;overflow:hidden;position:relative}
.pdf-viewer-panel{display:flex;flex-direction:column;background:var(--bg-main);flex:none;border-right:1px solid var(--border-color)}
.pdf-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px;background:var(--input-bg);border-bottom:1px solid var(--border-color)}
.pdf-title{font-size:.85rem;font-weight:600;color:var(--text-main);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px}
.pdf-search-bar{display:flex;align-items:center;gap:8px;background:var(--bg-main);border:1px solid var(--border-color);padding:4px 10px;border-radius:8px;flex:1}
.pdf-search-bar input{flex:1;background:transparent;border:none;outline:none;color:var(--text-main);font-size:.85rem;min-width:100px}
.search-icon{font-size:.8rem;color:var(--text-muted)}
.search-spinner{width:14px;height:14px;border:2px solid var(--border-color);border-top-color:var(--primary);border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.search-nav{display:flex;align-items:center;gap:4px;font-size:.8rem}
.match-count{color:var(--text-muted);margin-right:4px;font-weight:500}
.match-count.no-result{color:#ef4444}
.search-nav button{background:var(--sidebar-bg);border:1px solid var(--border-color);color:var(--text-main);border-radius:4px;padding:2px 6px;cursor:pointer}
.search-nav button:hover{background:var(--hover-bg);color:var(--primary);border-color:var(--primary)}
.clear-search-btn{color:#ef4444!important;border-color:transparent!important}
.close-pdf-btn{background:transparent;border:none;color:var(--text-muted);cursor:pointer;font-size:1.1rem}
.close-pdf-btn:hover{color:#ef4444}
.pdf-frame{width:100%;flex:1;border:none}
.resizer{width:8px;background-color:var(--border-color);cursor:col-resize;display:flex;align-items:center;justify-content:center;z-index:5}
.resizer:hover,.resizer.is-resizing{background-color:var(--primary)}
.resizer-handle{width:2px;height:30px;background-color:rgba(128,128,128,.5);border-radius:2px}
.main-chat{flex:1;display:flex;flex-direction:column;height:100%;min-width:300px}
.messages-container{flex:1;overflow-y:auto;padding:24px 32px;display:flex;flex-direction:column;gap:16px}
.welcome-screen{text-align:center;color:var(--text-muted);margin:10vh auto 0;max-width:500px}
.welcome-icon{font-size:3rem;margin-bottom:16px}
.welcome-screen h2{font-size:1.5rem;color:var(--text-main);margin-bottom:10px}
.welcome-screen p{font-size:.95rem;line-height:1.5;margin-bottom:24px}
.welcome-upload-btn{display:inline-block;background:var(--primary);color:#fff;padding:12px 24px;border-radius:8px;font-weight:600;cursor:pointer}
.message-row{display:flex;align-items:flex-end;gap:10px;width:100%}
.user-row{justify-content:flex-end}
.bot-row{justify-content:flex-start}
.bot-avatar{width:32px;height:32px;border-radius:50%;background:var(--sidebar-bg);border:1px solid var(--border-color);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.chat-bubble{max-width:75%;padding:12px 18px;border-radius:16px;font-size:.95rem;line-height:1.6;word-break:break-word;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.user-bubble{background:var(--primary);color:#fff;border-bottom-right-radius:4px}
.bot-bubble{background:var(--chat-bubble-bot);color:var(--text-main);border:1px solid var(--border-color);border-bottom-left-radius:4px}
.live-thinking{color:var(--text-muted);font-style:italic;font-size:.88rem;border:1px dashed var(--border-color)}
.source-buttons{margin-top:12px;padding-top:12px;border-top:1px solid var(--border-color)}
.source-title{font-size:.75rem;color:var(--text-muted);font-weight:600;margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px}
.source-list{display:flex;gap:8px;flex-wrap:wrap}
.source-btn{background:var(--sidebar-bg);border:1px solid var(--border-color);color:var(--text-main);padding:4px 12px;border-radius:6px;font-size:.8rem;cursor:pointer}
.source-btn:hover,.source-btn.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.out-of-context-card{background:var(--sidebar-bg)!important;border:1px solid var(--border-color)!important;border-radius:12px!important;padding:16px!important;max-width:550px}
.ooc-header{font-weight:600;color:#fbbf24;margin-bottom:8px;font-size:1rem}
.ooc-body{font-size:.9rem;color:var(--text-main);line-height:1.5}
.upload-progress-bubble{width:100%;max-width:400px;padding:16px!important}
.upload-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:.9rem}
.upload-percent{font-size:.85rem;font-weight:bold}
.progress-bar-bg{width:100%;height:6px;background:var(--border-color);border-radius:4px;margin-bottom:16px;overflow:hidden}
.progress-bar-fill{height:100%;background:var(--primary);transition:width .15s linear}
.upload-steps{list-style:none;margin:0;padding:0;font-size:.85rem;color:var(--text-muted)}
.upload-steps li{margin-bottom:6px;display:flex;align-items:center;gap:8px}
.upload-steps li.done{color:var(--text-main)}
.step-icon{display:inline-block;width:14px;text-align:center}
.markdown-body{line-height:1.65}
.markdown-body h1,.markdown-body h2,.markdown-body h3,.markdown-body h4{font-size:1.05rem;font-weight:600;color:var(--text-main);margin-bottom:8px;line-height:1.4}
.markdown-body h1{font-size:1.15rem}.markdown-body h2{font-size:1.1rem}.markdown-body h3{font-size:1.05rem}
.markdown-body p{margin-bottom:8px}.markdown-body p:last-child{margin-bottom:0}
.markdown-body ul,.markdown-body ol{margin:6px 0 6px 20px}.markdown-body li{margin-bottom:4px}
.markdown-body code{background:var(--hover-bg);color:var(--primary);padding:2px 5px;border-radius:4px;font-weight:500}
.markdown-body pre{overflow-x:auto;background:var(--sidebar-bg);border:1px solid var(--border-color);color:var(--text-main);padding:12px;border-radius:8px;margin:10px 0}
.markdown-body blockquote{border-left:3px solid var(--primary);padding-left:12px;color:var(--text-muted)}
.thought-container{margin-bottom:10px;padding:8px 12px;background:var(--hover-bg);border:1px solid var(--border-color);border-radius:8px}
.thought-summary{cursor:pointer;color:var(--text-main);font-weight:600;font-size:.9rem}
.thought-content{margin-top:8px;padding-top:8px;border-top:1px dashed var(--border-color);color:var(--text-muted);font-style:italic;white-space:pre-wrap;font-size:.85rem}
.bubble-actions{display:flex;justify-content:flex-end;margin-top:8px;padding-top:4px;border-top:1px solid var(--border-color)}
.copy-btn{background:transparent;border:none;font-size:.75rem;color:var(--text-muted);cursor:pointer;padding:2px 6px}.copy-btn:hover{color:var(--primary)}
.user-actions{border-top:1px solid rgba(255,255,255,.2)}.user-actions .copy-btn{color:rgba(255,255,255,.8)}.user-actions .copy-btn:hover{background:rgba(255,255,255,.15);color:#fff}
.input-container{padding:16px 32px 24px;background:var(--input-bg);display:flex;flex-direction:column;align-items:center;border-top:1px solid var(--border-color)}
.active-file-tag{max-width:850px;width:100%;font-size:.85rem;color:var(--primary);background:var(--hover-bg);border:1px solid var(--border-color);padding:6px 14px;border-radius:6px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center}
.active-file-tag.selected{border-color:var(--primary);background:var(--hover-bg)}
.reopen-pdf-btn{background:var(--primary);color:#fff;border:none;padding:2px 8px;border-radius:4px;cursor:pointer}
.input-box{max-width:850px;width:100%;display:flex;align-items:center;gap:10px;background:var(--input-bg);border:1px solid var(--border-color);border-radius:12px;padding:6px 12px}
.input-box:focus-within{border-color:var(--primary)}
.attach-btn{color:var(--text-muted);cursor:pointer;display:flex;align-items:center;padding:6px}.attach-btn:hover{color:var(--primary)}.attach-btn.disabled{opacity:.5;cursor:not-allowed}
.model-select{background:var(--sidebar-bg);color:var(--text-main);border:1px solid var(--border-color);border-radius:8px;padding:6px;font-size:0.85rem;outline:none;cursor:pointer;margin-right:4px}
.model-select:focus,.model-select:hover{border-color:var(--primary)}
.model-select:disabled{opacity:0.5;cursor:not-allowed}
.input-box input{flex:1;border:none;outline:none;padding:10px 4px;font-size:.95rem;background:transparent;color:var(--text-main)}
.send-btn,.stop-btn{padding:10px 20px;border:none;border-radius:8px;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center}
.send-btn{background:var(--primary);color:#fff}.send-btn:disabled{background:var(--border-color);cursor:not-allowed;color:var(--text-muted)}
.stop-btn{background:var(--input-bg);color:var(--text-main);border:1px solid var(--border-color)}.stop-btn.icon-only{padding:0;width:34px;height:34px;font-size:.9rem;border-radius:8px}
.disclaimer{font-size:.75rem;color:var(--text-muted);margin-top:10px}
@media(max-width:900px){.sidebar{width:220px!important;flex-basis:220px!important}.sidebar-resizer{display:none}.messages-container{padding:18px}.input-container{padding:12px 18px 18px}}
@media(max-width:700px){.sidebar{display:none}.pdf-viewer-panel{display:none!important}.resizer,.sidebar-resizer{display:none!important}.chat-bubble{max-width:90%}}
</style>
