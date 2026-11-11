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
                throw new ArgumentException("Choose a source and destination folder.");
            return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar);
        }

        private static void CopyTree(string source, string target)
        {
            if ((File.GetAttributes(source) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Linked source folders are not supported: " + source);
            Directory.CreateDirectory(target);
            foreach (string file in Directory.GetFiles(source))
            {
                string name = Path.GetFileName(file);
                if ((File.GetAttributes(file) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Linked source files are not supported: " + file);
                File.Copy(file, Path.Combine(target, name));
            }
            foreach (string directory in Directory.GetDirectories(source))
                CopyTree(directory, Path.Combine(target, Path.GetFileName(directory)));
        }

        public static void Install(string sourceFolder, string targetFolder,
            bool copySaves, Action<string> progress)
        {
            string source = Canonical(sourceFolder);
            string target = Canonical(targetFolder);
            if (!Directory.Exists(source)) throw new DirectoryNotFoundException(source);
            string sourceWithSlash = source + Path.DirectorySeparatorChar;
            string targetWithSlash = target + Path.DirectorySeparatorChar;
            if (String.Equals(source, target, StringComparison.OrdinalIgnoreCase) ||
                target.StartsWith(sourceWithSlash, StringComparison.OrdinalIgnoreCase) ||
                source.StartsWith(targetWithSlash, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException(
                    "The destination must be separate from the GOG game folder.");
            if (Directory.Exists(target) && Directory.GetFileSystemEntries(target).Length != 0)
                throw new InvalidOperationException("Choose an empty destination folder.");

            string executable = Path.Combine(source, "Eden.exe");
            if (!File.Exists(executable))
                throw new FileNotFoundException("Eden.exe was not found in the GOG folder.");
            string[] directories = { "Images", "Levels", "Movies", "Sounds" };
            string[] files = { "d3d8.dll", "title.edf" };
            foreach (string name in directories)
                if (!Directory.Exists(Path.Combine(source, name)))
                    throw new DirectoryNotFoundException("Missing game folder: " + name);
            foreach (string name in files)
                if (!File.Exists(Path.Combine(source, name)))
                    throw new FileNotFoundException("Missing game file: " + name);

            progress("Verifying the GOG executable...");
            PatchManifest manifest = PatchManifest.Load();
            byte[] original = File.ReadAllBytes(executable);
            byte[] game = new byte[manifest.OutputLength];
            using (SHA256 hash = SHA256.Create())
            {
                if (original.Length != manifest.SourceLength ||
                    !Equal(hash.ComputeHash(original), manifest.SourceHash))
                    throw new InvalidDataException(
                        "This setup supports only the verified GOG Eden.exe version 1.0.0.2.");
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

            Directory.CreateDirectory(target);
            foreach (string name in directories)
            {
                progress("Copying " + name + "...");
                CopyTree(Path.Combine(source, name), Path.Combine(target, name));
            }
            foreach (string name in files)
            {
                progress("Copying " + name + "...");
                File.Copy(Path.Combine(source, name), Path.Combine(target, name));
            }
            if (copySaves && Directory.Exists(Path.Combine(source, "SAVED GAMES")))
            {
                progress("Copying saved games...");
                CopyTree(Path.Combine(source, "SAVED GAMES"),
                    Path.Combine(target, "SAVED GAMES"));
            }
            else Directory.CreateDirectory(Path.Combine(target, "SAVED GAMES"));
            Directory.CreateDirectory(Path.Combine(target, "ScreenShots"));
            progress("Writing the patched executable...");
            File.WriteAllBytes(Path.Combine(target, "Eden.exe"), game);
            progress("Installation complete.");
        }
    }

    internal sealed class SetupWindow : Form
    {
        private readonly TextBox source = new TextBox();
        private readonly TextBox target = new TextBox();
        private readonly CheckBox saves = new CheckBox();
        private readonly Button install = new Button();
        private readonly Label status = new Label();
        private readonly ProgressBar progress = new ProgressBar();
        private readonly BackgroundWorker worker = new BackgroundWorker();

        public SetupWindow()
        {
            Text = "Project Eden Unofficial Patch Setup";
            ClientSize = new Size(650, 285);
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
            sourceBrowse.Click += delegate { Browse(source, false); };

            Label targetLabel = new Label();
            targetLabel.Text = "New patched game folder (must be empty)";
            targetLabel.SetBounds(20, 85, 550, 20);
            target.SetBounds(20, 109, 515, 24);
            Button targetBrowse = new Button();
            targetBrowse.Text = "Browse...";
            targetBrowse.SetBounds(545, 108, 85, 26);
            targetBrowse.Click += delegate { Browse(target, true); };

            saves.Text = "Copy saved games from the GOG installation";
            saves.SetBounds(20, 149, 500, 25);
            install.Text = "Install";
            install.SetBounds(530, 183, 100, 30);
            install.Click += BeginInstall;
            progress.SetBounds(20, 227, 610, 16);
            status.Text = "Choose folders to create a separate patched installation.";
            status.SetBounds(20, 252, 610, 22);

            Controls.AddRange(new Control[] { sourceLabel, source, sourceBrowse,
                targetLabel, target, targetBrowse, saves, install,
                progress, status });
            worker.WorkerReportsProgress = true;
            worker.DoWork += delegate(object sender, DoWorkEventArgs e)
            {
                string[] paths = (string[])e.Argument;
                Installer.Install(paths[0], paths[1], paths[2] == "1",
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
                    status.Text = "Installation stopped. The destination may contain partial files.";
                    MessageBox.Show(this, e.Error.Message, "Setup failed",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
                else
                {
                    status.Text = "Installation complete. Launch Eden.exe from the new folder.";
                    MessageBox.Show(this, "The separate patched game is ready.",
                        "Setup complete", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            };
        }

        private void Browse(TextBox box, bool allowNew)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.ShowNewFolderButton = allowNew;
                if (Directory.Exists(box.Text)) dialog.SelectedPath = box.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK) box.Text = dialog.SelectedPath;
            }
        }

        private void BeginInstall(object sender, EventArgs e)
        {
            install.Enabled = false;
            progress.Style = ProgressBarStyle.Marquee;
            worker.RunWorkerAsync(new string[] { source.Text, target.Text,
                saves.Checked ? "1" : "0" });
        }
    }

    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length >= 3 && args[0] == "--install")
            {
                try
                {
                    Installer.Install(args[1], args[2],
                        Array.IndexOf(args, "--copy-saves") >= 0,
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
