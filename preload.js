const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  chatOpen:    () => ipcRenderer.send('chat-open'),
  chatClose:   () => ipcRenderer.send('chat-close'),
  panelOpen:   () => ipcRenderer.send('panel-open'),
  panelClose:  () => ipcRenderer.send('panel-close'),
})
