using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Threading;
using System.Windows.Forms;

namespace Ermes
{
    static class Program
    {
        private static NotifyIcon trayIcon;
        private static Process backendProcess;
        private static Process browserProcess;
        private static Mutex singleInstanceMutex;
        private const string AppMutexName = "Global\\ErmesKnowledgeAppMutex_8502";
        private const int BackendPort = 8502;
        private const string AppUrl = "http://127.0.0.1:8502/";

        [STAThread]
        static void Main()
        {
            bool createdNew;
            singleInstanceMutex = new Mutex(true, AppMutexName, out createdNew);
            if (!createdNew)
            {
                // App is already running, open URL in browser and exit this instance
                OpenAppWindow();
                return;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            // Initialize tray icon
            InitializeTray();

            // Background worker thread for initialization
            Thread initThread = new Thread(InitializeAndLaunch);
            initThread.IsBackground = true;
            initThread.Start();

            Application.Run();
        }

        private static void InitializeTray()
        {
            ContextMenu contextMenu = new ContextMenu();
            contextMenu.MenuItems.Add("Apri Ermes", (s, e) => OpenAppWindow());
            contextMenu.MenuItems.Add("Verifica Stato", (s, e) => CheckStatusAndNotify());
            contextMenu.MenuItems.Add("-");
            contextMenu.MenuItems.Add("Esci da Ermes", (s, e) => ExitApp());

            trayIcon = new NotifyIcon();
            trayIcon.Text = "Ermes Knowledge RAG";
            
            // Try loading Ermes.ico
            string iconPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Ermes.ico");
            if (File.Exists(iconPath))
            {
                try
                {
                    trayIcon.Icon = new Icon(iconPath);
                }
                catch
                {
                    trayIcon.Icon = SystemIcons.Application;
                }
            }
            else
            {
                trayIcon.Icon = SystemIcons.Application;
            }

            trayIcon.ContextMenu = contextMenu;
            trayIcon.Visible = true;
            trayIcon.DoubleClick += (s, e) => OpenAppWindow();
        }

        private static void InitializeAndLaunch()
        {
            try
            {
                ShowNotification("Ermes", "Avvio dei componenti in corso...", ToolTipIcon.Info);

                // 1. Ensure Ollama is running
                EnsureOllama();

                // 2. Ensure Backend is running
                EnsureBackend();

                // 3. Open Ermes in native desktop app window
                OpenAppWindow();

                ShowNotification("Ermes Attivo", "Ermes e' pronto all'uso.", ToolTipIcon.Info);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Errore durante l'avvio di Ermes:\n" + ex.Message, "Ermes - Errore", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private static void ShowNotification(string title, string message, ToolTipIcon icon)
        {
            if (trayIcon != null)
            {
                trayIcon.BalloonTipTitle = title;
                trayIcon.BalloonTipText = message;
                trayIcon.BalloonTipIcon = icon;
                trayIcon.ShowBalloonTip(3000);
            }
        }

        private static bool CheckUrl(string url, int timeoutMs = 2000)
        {
            try
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
                request.Timeout = timeoutMs;
                request.Method = "GET";
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                {
                    return response.StatusCode == HttpStatusCode.OK;
                }
            }
            catch
            {
                return false;
            }
        }

        private static void EnsureOllama()
        {
            if (CheckUrl("http://127.0.0.1:11434/api/tags", 2000))
            {
                return; // Ollama is already running
            }

            // Look for Ollama executable
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);

            string[] candidatePaths = new string[]
            {
                Path.Combine(localAppData, @"Programs\Ollama\ollama.exe"),
                Path.Combine(programFiles, @"Ollama\ollama.exe"),
                "ollama.exe"
            };

            foreach (string exe in candidatePaths)
            {
                if (File.Exists(exe) || exe == "ollama.exe")
                {
                    try
                    {
                        ProcessStartInfo psi = new ProcessStartInfo();
                        psi.FileName = exe;
                        psi.Arguments = "serve";
                        psi.CreateNoWindow = true;
                        psi.UseShellExecute = false;
                        psi.WindowStyle = ProcessWindowStyle.Hidden;
                        Process.Start(psi);
                        break;
                    }
                    catch { }
                }
            }

            // Wait up to 6 seconds for Ollama
            for (int i = 0; i < 6; i++)
            {
                Thread.Sleep(1000);
                if (CheckUrl("http://127.0.0.1:11434/api/tags", 1000))
                    break;
            }
        }

        private static void EnsureBackend()
        {
            if (CheckUrl(AppUrl + "health", 2500))
            {
                return; // Backend is already running
            }

            string baseDir = AppDomain.CurrentDomain.BaseDirectory;

            // Locate Python interpreter
            string[] pythonCandidates = new string[]
            {
                Path.Combine(baseDir, @".venv-ermes\Scripts\python.exe"),
                Path.Combine(baseDir, @"python\python.exe"),
                Path.Combine(baseDir, @"runtime\python.exe"),
                "python.exe"
            };

            string pythonExe = null;
            foreach (string candidate in pythonCandidates)
            {
                if (File.Exists(candidate))
                {
                    pythonExe = candidate;
                    break;
                }
            }

            if (pythonExe == null)
            {
                pythonExe = "python.exe"; // Fallback to PATH
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExe;
            psi.Arguments = "-m uvicorn api:app --host 127.0.0.1 --port " + BackendPort;
            psi.WorkingDirectory = baseDir;
            psi.CreateNoWindow = true;
            psi.UseShellExecute = false;
            psi.WindowStyle = ProcessWindowStyle.Hidden;

            try
            {
                backendProcess = Process.Start(psi);
            }
            catch (Exception ex)
            {
                throw new Exception("Impossibile avviare il motore Python:\n" + ex.Message);
            }

            // Poll for backend readiness up to 15 seconds
            bool ready = false;
            for (int i = 0; i < 15; i++)
            {
                Thread.Sleep(1000);
                if (CheckUrl(AppUrl + "health", 1500))
                {
                    ready = true;
                    break;
                }
            }

            if (!ready)
            {
                throw new Exception("Il server Ermes non ha risposto entro i tempi previsti sulla porta " + BackendPort);
            }
        }

        private static void OpenAppWindow()
        {
            string edge = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Microsoft\Edge\Application\msedge.exe");
            if (!File.Exists(edge))
            {
                edge = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Microsoft\Edge\Application\msedge.exe");
            }

            string chrome = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"Google\Chrome\Application\chrome.exe");
            if (!File.Exists(chrome))
            {
                chrome = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), @"Google\Chrome\Application\chrome.exe");
            }

            string browserExe = File.Exists(edge) ? edge : (File.Exists(chrome) ? chrome : null);

            if (browserExe != null)
            {
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo();
                    psi.FileName = browserExe;
                    psi.Arguments = "--app=" + AppUrl;
                    browserProcess = Process.Start(psi);
                    return;
                }
                catch { }
            }

            // Fallback to default browser
            try
            {
                Process.Start(AppUrl);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Errore apertura browser: " + ex.Message);
            }
        }

        private static void CheckStatusAndNotify()
        {
            bool backendOk = CheckUrl(AppUrl + "health", 2000);
            bool ollamaOk = CheckUrl("http://127.0.0.1:11434/api/tags", 2000);

            string msg = "Backend Ermes: " + (backendOk ? "Attivo" : "Non raggiungibile") + "\n" +
                         "Motore Ollama: " + (ollamaOk ? "Attivo" : "Non raggiungibile");

            ShowNotification("Stato Ermes", msg, backendOk ? ToolTipIcon.Info : ToolTipIcon.Warning);
        }

        private static void ExitApp()
        {
            try
            {
                if (trayIcon != null)
                {
                    trayIcon.Visible = false;
                    trayIcon.Dispose();
                }

                // Close spawned backend if started by launcher
                if (backendProcess != null && !backendProcess.HasExited)
                {
                    try
                    {
                        backendProcess.Kill();
                    }
                    catch { }
                }
            }
            finally
            {
                if (singleInstanceMutex != null)
                {
                    singleInstanceMutex.ReleaseMutex();
                }
                Application.Exit();
                Environment.Exit(0);
            }
        }
    }
}
