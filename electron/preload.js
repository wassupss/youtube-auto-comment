const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  openFile: (filters) => ipcRenderer.invoke("dialog:openFile", filters),
  saveFile: (defaultName, filters) =>
    ipcRenderer.invoke("dialog:saveFile", defaultName, filters),
  saveBuffer: (filePath, buffer) =>
    ipcRenderer.invoke("fs:saveBuffer", filePath, buffer),
});
