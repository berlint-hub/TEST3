# TEST3

## Build QualityScaler (Windows .exe)

Workflow [`.github/workflows/build-qualityscaler.yml`](.github/workflows/build-qualityscaler.yml)
zkompiluje [Djdefrag/QualityScaler](https://github.com/Djdefrag/QualityScaler) na Windows
runneru pomocí PyInstalleru a výsledek nahraje jako artifact **`QualityScaler-windows-x64`**.

### Jak spustit

- Automaticky: při push změny workflow souboru.
- Ručně: **Actions → Build QualityScaler (Windows .exe) → Run workflow**
  (volitelně lze zadat jiný commit/tag QualityScaleru a verzi Pythonu), nebo:

  ```bash
  gh workflow run build-qualityscaler.yml --ref <branch>
  gh run download --name QualityScaler-windows-x64
  ```

### Co obsahuje výsledek

```
QualityScaler/
├── QualityScaler.exe
├── Assets/        ikony + ffmpeg.exe
├── AI-onnx/       ← sem nakopíruj stažené *.onnx modely (nejsou součástí buildu)
└── …              runtime (python, onnxruntime-directml, DirectML.dll, …)
```

AI modely autor distribuuje mimo GitHub – odkaz je v
[README QualityScaleru](https://github.com/Djdefrag/QualityScaler#-make-it-work-by-yourself).
