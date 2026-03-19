const { app, BrowserWindow, ipcMain, screen } = require('electron')
const { spawn } = require('child_process')
const path = require('path')

let win = null
let serverProcess = null

const DOCK_W = 540   // 실제 콘텐츠 너비 ~519px + 여유
const DOCK_H = 175
const PANEL_H = 680
const PANEL_W = 980

function startServer() {
  const logPath = path.join(__dirname, 'server.log')
  const fs = require('fs')
  const out = fs.openSync(logPath, 'a')
  const err = fs.openSync(logPath, 'a')

  serverProcess = spawn(
    path.join(__dirname, 'venv/bin/python3'),
    [path.join(__dirname, 'server_v3.py')],
    {
      cwd: __dirname,
      detached: true,      // 완전 백그라운드
      stdio: ['ignore', out, err],  // 터미널 없이 로그파일로
    }
  )
  serverProcess.unref()  // Electron 종료해도 별도로 관리
}

function getDockBounds() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize
  return {
    width:  DOCK_W,
    height: DOCK_H,
    x: Math.floor((width  - DOCK_W) / 2),
    y: height - DOCK_H - 4,
  }
}

function createWindow() {
  const b = getDockBounds()

  win = new BrowserWindow({
    ...b,
    frame: false,
    transparent: true,
    alwaysOnTop: false,
    resizable: false,
    movable: true,
    hasShadow: false,
    skipTaskbar: true,
    backgroundColor: '#00000000',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  setTimeout(() => win.loadURL('http://127.0.0.1:5050/voice'), 2000)
  win.on('closed', () => { win = null })
}

// 채팅 열기 — 창을 위로 확장 (하단 고정)
ipcMain.on('chat-open', () => {
  if (!win) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  const cur = win.getBounds()
  win.setBounds({
    x: Math.floor((width - DOCK_W) / 2),
    y: cur.y + cur.height - PANEL_H,
    width:  DOCK_W,
    height: PANEL_H,
  }, false)
})

ipcMain.on('chat-close', () => {
  if (!win) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  const cur = win.getBounds()
  win.setBounds({
    x: Math.floor((width - DOCK_W) / 2),
    y: cur.y + cur.height - DOCK_H,
    width:  DOCK_W,
    height: DOCK_H,
  }, false)
})

ipcMain.on('panel-open', () => {
  if (!win) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  const cur = win.getBounds()
  win.setBounds({
    x: Math.floor((width - PANEL_W) / 2),
    y: cur.y + cur.height - PANEL_H,
    width:  PANEL_W,
    height: PANEL_H,
  }, false)
})

ipcMain.on('panel-close', () => {
  if (!win) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  const cur = win.getBounds()
  win.setBounds({
    x: Math.floor((width - DOCK_W) / 2),
    y: cur.y + cur.height - DOCK_H,
    width:  DOCK_W,
    height: DOCK_H,
  }, false)
})

app.whenReady().then(() => {
  startServer()
  createWindow()
})

app.on('window-all-closed', () => {
  if (serverProcess) {
    try { process.kill(-serverProcess.pid) } catch {}
  }
  app.quit()
})