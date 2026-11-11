using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;

namespace ProjectEdenUnofficialSetup
{
    internal sealed class Change
    {
        public int Offset;
        public byte[] Expected;
        public byte[] Replacement;
    }

    internal sealed class PatchManifest
    {
        public byte[] SourceHash;
        public byte[] OutputHash;
        public int SourceLength;
        public int OutputLength;
        public List<Change> Changes = new List<Change>();

        public static PatchManifest Load()
        {
            Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(
                "ProjectEdenPatchManifest");
            if (resource == null) throw new InvalidDataException("Patch data is missing.");
            using (resource)
            using (BinaryReader reader = new BinaryReader(resource))
            {
                if (Encoding.ASCII.GetString(reader.ReadBytes(10)) != "EDENPATCH2")
                    throw new InvalidDataException("Patch data has an invalid header.");
                PatchManifest manifest = new PatchManifest();
                manifest.SourceHash = reader.ReadBytes(32);
                manifest.OutputHash = reader.ReadBytes(32);
                manifest.SourceLength = reader.ReadInt32();
                manifest.OutputLength = reader.ReadInt32();
                int count = reader.ReadInt32();
                if (manifest.SourceHash.Length != 32 || manifest.OutputHash.Length != 32 ||
                    manifest.SourceLength <= 0 ||
                    manifest.OutputLength < manifest.SourceLength ||
                    count <= 0 || count > 10000)
                    throw new InvalidDataException("Patch data is incomplete.");
                for (int index = 0; index < count; index++)
                {
                    Change change = new Change();
                    change.Offset = reader.ReadInt32();
                    int expectedLength = reader.ReadInt32();
                    int replacementLength = reader.ReadInt32();
                    if (change.Offset < 0 || expectedLength < 0 ||
                        replacementLength < 0 ||
                        expectedLength + replacementLength == 0 ||
                        change.Offset > manifest.SourceLength - expectedLength ||
                        change.Offset > manifest.OutputLength - replacementLength)
                        throw new InvalidDataException("Patch range is invalid.");
                    change.Expected = reader.ReadBytes(expectedLength);
                    change.Replacement = reader.ReadBytes(replacementLength);
                    if (change.Expected.Length != expectedLength ||
                        change.Replacement.Length != replacementLength)
                        throw new InvalidDataException("Patch range is incomplete.");
                    manifest.Changes.Add(change);
                }
                if (resource.Position != resource.Length)
                    throw new InvalidDataException("Patch data has trailing bytes.");
                return manifest;
            }
        }
    }

    internal static class Installer
    {
        private static bool Equal(byte[] left, byte[] right)
        {
            if (left.Length != right.Length) return false;
            for (int index = 0; index < left.Length; index++)
                if (left[index] != right[index]) return false;
            return true;
        }

        private static string Canonical(string path)
        {
            if (String.IsNullOrWhiteSpace(path))
                throw new ArgumentException("Choose the GOG Project Eden folder.");
            return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar);
        }

        public static void Install(string gameFolder, Action<string> progress)
        {
            string folder = Canonical(gameFolder);
            if (!Directory.Exists(folder)) throw new DirectoryNotFoundException(folder);
            string executable = Path.Combine(folder, "Eden.exe");
            string backup = Path.Combine(folder, "Eden.exe.original");
            if (!File.Exists(executable))
                throw new FileNotFoundException("Eden.exe was not found in the GOG folder.");

            progress("Verifying the GOG executable...");
            PatchManifest manifest = PatchManifest.Load();
            byte[] original = File.ReadAllBytes(executable);
            byte[] game;
            using (SHA256 hash = SHA256.Create())
            {
                if (original.Length == manifest.OutputLength &&
                    Equal(hash.ComputeHash(original), manifest.OutputHash))
                {
                    if (!File.Exists(backup) ||
                        !Equal(hash.ComputeHash(File.ReadAllBytes(backup)), manifest.SourceHash))
                        throw new InvalidDataException(
                            "Eden.exe is already patched, but its original backup is missing or invalid.");
                    progress("The patch is already installed.");
                    return;
                }
                if (original.Length != manifest.SourceLength ||
                    !Equal(hash.ComputeHash(original), manifest.SourceHash))
                    throw new InvalidDataException(
                        "This setup supports only the verified GOG Eden.exe version 1.0.0.2.");
                if (File.Exists(backup) &&
                    !Equal(hash.ComputeHash(File.ReadAllBytes(backup)), manifest.SourceHash))
                    throw new InvalidDataException(
                        "Eden.exe.original already exists and is not the verified GOG executable.");
                game = new byte[manifest.OutputLength];
                Buffer.BlockCopy(original, 0, game, 0, original.Length);
                foreach (Change change in manifest.Changes)
                {
                    byte[] actual = new byte[change.Expected.Length];
                    Buffer.BlockCopy(original, change.Offset, actual, 0, actual.Length);
                    if (!Equal(actual, change.Expected))
                        throw new InvalidDataException("A patch byte did not match the GOG executable.");
                    Buffer.BlockCopy(change.Replacement, 0, game,
                        change.Offset, change.Replacement.Length);
                }
                if (!Equal(hash.ComputeHash(game), manifest.OutputHash))
                    throw new InvalidDataException("The patched executable failed verification.");
            }

            progress("Backing up and patching Eden.exe...");
            string staged = Path.Combine(folder,
                "Eden.exe.patch-" + Guid.NewGuid().ToString("N") + ".tmp");
            try
            {
                File.WriteAllBytes(staged, game);
                File.Replace(staged, executable, File.Exists(backup) ? null : backup);
            }
            finally
            {
                if (File.Exists(staged)) File.Delete(staged);
            }
            progress("Installation complete.");
        }
    }

    internal sealed class SetupWindow : Form
    {
        private readonly TextBox source = new TextBox();
        private readonly Button install = new Button();
        private readonly Label status = new Label();
        private readonly ProgressBar progress = new ProgressBar();
        private readonly BackgroundWorker worker = new BackgroundWorker();

        public SetupWindow()
        {
            Text = "Project Eden Unofficial Patch Setup";
            ClientSize = new Size(650, 185);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;

            Label sourceLabel = new Label();
            sourceLabel.Text = "GOG Project Eden folder";
            sourceLabel.SetBounds(20, 18, 550, 20);
            source.SetBounds(20, 42, 515, 24);
            Button sourceBrowse = new Button();
            sourceBrowse.Text = "Browse...";
            sourceBrowse.SetBounds(545, 41, 85, 26);
            sourceBrowse.Click += delegate { Browse(source); };

            install.Text = "Install";
            install.SetBounds(530, 82, 100, 30);
            install.Click += BeginInstall;
            progress.SetBounds(20, 125, 610, 16);
            status.Text = "The original Eden.exe will be backed up in the selected folder.";
            status.SetBounds(20, 150, 610, 22);

            Controls.AddRange(new Control[] { sourceLabel, source, sourceBrowse,
                install, progress, status });
            worker.WorkerReportsProgress = true;
            worker.DoWork += delegate(object sender, DoWorkEventArgs e)
            {
                Installer.Install((string)e.Argument,
                    delegate(string message) { worker.ReportProgress(0, message); });
            };
            worker.ProgressChanged += delegate(object sender, ProgressChangedEventArgs e)
            {
                status.Text = (string)e.UserState;
            };
            worker.RunWorkerCompleted += delegate(object sender, RunWorkerCompletedEventArgs e)
            {
                progress.Style = ProgressBarStyle.Blocks;
                install.Enabled = true;
                if (e.Error != null)
                {
                    status.Text = "Installation stopped. See the error for details.";
                    MessageBox.Show(this, e.Error.Message, "Setup failed",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                else
                {
                    status.Text = "Installation complete. Launch Eden.exe from the GOG folder.";
                    MessageBox.Show(this, "Project Eden is patched in its GOG folder.",
                        "Setup complete", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            };
        }

        private void Browse(TextBox box)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.ShowNewFolderButton = false;
                if (Directory.Exists(box.Text)) dialog.SelectedPath = box.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK) box.Text = dialog.SelectedPath;
            }
        }

        private void BeginInstall(object sender, EventArgs e)
        {
            install.Enabled = false;
            progress.Style = ProgressBarStyle.Marquee;
            worker.RunWorkerAsync(source.Text);
        }
    }

    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length > 0)
            {
                if (args.Length != 2 || args[0] != "--install")
                {
                    Console.Error.WriteLine("Usage: ProjectEdenUnofficialSetup.exe --install <GOG game folder>");
                    return 2;
                }
                try
                {
                    Installer.Install(args[1],
                        delegate(string message) { Console.WriteLine(message); });
                    return 0;
                }
                catch (Exception error)
                {
                    Console.Error.WriteLine(error);
                    return 1;
                }
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupWindow());
            return 0;
        }
    }
}
