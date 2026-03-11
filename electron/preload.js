const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("api", {
  openFile: (filters) => ipcRenderer.invoke("dialog:openFile", filters),
});
