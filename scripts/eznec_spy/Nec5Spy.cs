// Nec5Spy — a log-and-delegate shim that stands in for EZNEC's NEC-5 engine.
//
// EZNEC Pro+ v7 launches its external engine as `C:\EZNEC 7.0\Docs\NEC5CL_x13.exe`
// (see LastRun.log: "Running ext engine ..."). install.ps1 renames the real binary
// to NEC5CL_x13.real.exe and drops this shim in its place, so every calculation the
// user runs from the GUI is captured: argv, cwd, stdin/stdout/stderr, and the files
// the parent wrote before the run and read after it.
//
// Design rules, in priority order:
//   1. Never break the EZNEC session. Every capture step is wrapped; on any failure
//      the shim still delegates and still returns the real engine's exit code.
//   2. Never change the protocol. stdin/stdout/stderr are *pumped* (tee'd), not
//      read to EOF, so a prompt-driven conversational engine cannot deadlock.
//   3. Observe I/O only. Nothing here inspects the binary — black-box, per momwire#390.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

internal static class Nec5Spy
{
    // build.ps1 rewrites this token. If it survives, we fall back to %TEMP%.
    private const string CaptureRootToken = "__CAPTURE_ROOT__";

    // Real engine sits beside us with this suffix inserted before .exe.
    private const string RealSuffix = ".real";

    // Copy captured files up to this size; larger ones are manifest+hash only.
    private const long MaxCopyBytes = 4L * 1024 * 1024;

    // Never copy these (the engine binary itself, the 737 KB Sommerfeld table).
    private static readonly HashSet<string> NoCopyExt = new HashSet<string>(
        StringComparer.OrdinalIgnoreCase) { ".exe", ".dll", ".nex", ".pdb" };

    private static string _captureDir;
    private static readonly StringBuilder Meta = new StringBuilder();

    private static int Main()
    {
        string realExe = null;
        try
        {
            realExe = ResolveRealEngine();
        }
        catch (Exception ex)
        {
            // Without the real engine there is nothing to delegate to. Say so loudly
            // on stderr — EZNEC will surface a failed calculation rather than hang.
            Console.Error.WriteLine("NEC5SPY: cannot locate the real engine: " + ex.Message);
            return 9009;
        }

        try { BeginCapture(realExe); } catch { /* capture is best-effort */ }

        int exitCode;
        var sw = Stopwatch.StartNew();
        try
        {
            exitCode = Delegate(realExe);
        }
        catch (Exception ex)
        {
            try { Note("delegate_error", ex.ToString()); FlushMeta(); } catch { }
            throw;
        }
        sw.Stop();

        try { EndCapture(realExe, exitCode, sw.ElapsedMilliseconds); } catch { }
        return exitCode;
    }

    // ---- delegation ---------------------------------------------------------

    private static string ResolveRealEngine()
    {
        string self = Process.GetCurrentProcess().MainModule.FileName;
        string dir = Path.GetDirectoryName(self);
        string stem = Path.GetFileNameWithoutExtension(self);
        string candidate = Path.Combine(dir, stem + RealSuffix + ".exe");
        if (!File.Exists(candidate))
            throw new FileNotFoundException("expected " + candidate);
        return candidate;
    }

    private static int Delegate(string realExe)
    {
        var psi = new ProcessStartInfo(realExe)
        {
            Arguments = ArgumentTail(Environment.CommandLine),
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = Directory.GetCurrentDirectory(),
        };

        using (var child = Process.Start(psi))
        {
            // stdin is a background pump: a console with no input never reaches EOF,
            // and we must not let that keep the shim alive after the child exits.
            StartPump(StdStream(ConsoleStream.In), child.StandardInput.BaseStream,
                      TeePath("stdin.bin"), background: true, closeSink: true);

            // The output pumps do end at the child's EOF, so we join them — otherwise
            // the tail of the printout could be lost on exit.
            var outputPumps = new[]
            {
                StartPump(child.StandardOutput.BaseStream, StdStream(ConsoleStream.Out),
                          TeePath("stdout.bin"), background: false, closeSink: false),
                StartPump(child.StandardError.BaseStream, StdStream(ConsoleStream.Error),
                          TeePath("stderr.bin"), background: false, closeSink: false),
            };

            child.WaitForExit();
            foreach (var t in outputPumps) t.Join(5000);
            return child.ExitCode;
        }
    }

    private enum ConsoleStream { In, Out, Error }

    /// EZNEC may launch the engine detached or with no console at all, in which case
    /// opening a standard stream throws. Capture is never worth failing a run over —
    /// fall back to a sink that swallows bytes so delegation still proceeds.
    private static Stream StdStream(ConsoleStream which)
    {
        try
        {
            switch (which)
            {
                case ConsoleStream.In: return Console.OpenStandardInput();
                case ConsoleStream.Out: return Console.OpenStandardOutput();
                default: return Console.OpenStandardError();
            }
        }
        catch { return Stream.Null; }
    }

    /// Copy source→sink byte-for-byte, flushing after every read so a prompt/response
    /// protocol still works, while tee'ing the same bytes to a capture file.
    private static Thread StartPump(Stream source, Stream sink, string teePath,
                                    bool background, bool closeSink)
    {
        var t = new Thread(() =>
        {
            FileStream tee = null;
            try { if (teePath != null) tee = new FileStream(teePath, FileMode.Create, FileAccess.Write); }
            catch { }
            try
            {
                var buf = new byte[4096];
                int n;
                while ((n = source.Read(buf, 0, buf.Length)) > 0)
                {
                    sink.Write(buf, 0, n);
                    sink.Flush();
                    if (tee != null) { try { tee.Write(buf, 0, n); tee.Flush(); } catch { } }
                }
            }
            catch { /* broken pipe on either side just ends this pump */ }
            finally
            {
                if (tee != null) { try { tee.Dispose(); } catch { } }
                if (closeSink) { try { sink.Dispose(); } catch { } }
            }
        });
        t.IsBackground = background;
        t.Start();
        return t;
    }

    /// Everything after the executable token of a Windows command line.
    private static string ArgumentTail(string commandLine)
    {
        if (string.IsNullOrEmpty(commandLine)) return string.Empty;
        int i = 0;
        if (commandLine[0] == '"')
        {
            i = commandLine.IndexOf('"', 1);
            i = (i < 0) ? commandLine.Length : i + 1;
        }
        else
        {
            while (i < commandLine.Length && commandLine[i] != ' ' && commandLine[i] != '\t') i++;
        }
        return commandLine.Substring(Math.Min(i, commandLine.Length)).TrimStart();
    }

    // ---- capture ------------------------------------------------------------

    private static string CaptureRoot()
    {
        string env = Environment.GetEnvironmentVariable("EZNEC_SPY_ROOT");
        if (!string.IsNullOrEmpty(env)) return env;
        if (CaptureRootToken.IndexOf("__CAPTURE", StringComparison.Ordinal) < 0)
            return CaptureRootToken;
        return Path.Combine(Path.GetTempPath(), "eznec-capture");
    }

    private static void BeginCapture(string realExe)
    {
        string root = CaptureRoot();
        Directory.CreateDirectory(root);

        int seq = 1;
        foreach (var d in Directory.GetDirectories(root))
        {
            string name = Path.GetFileName(d);
            int us = name.IndexOf('_');
            int val;
            if (us > 0 && int.TryParse(name.Substring(0, us), NumberStyles.Integer,
                                       CultureInfo.InvariantCulture, out val) && val >= seq)
                seq = val + 1;
        }

        // Directory creation is the sequence claim; retry if another run raced us.
        for (int attempt = 0; attempt < 50; attempt++, seq++)
        {
            string candidate = Path.Combine(root, string.Format(CultureInfo.InvariantCulture,
                "{0:D4}_{1:yyyyMMdd-HHmmss}", seq, DateTime.Now));
            if (Directory.Exists(candidate)) continue;
            try { Directory.CreateDirectory(candidate); _captureDir = candidate; break; }
            catch { }
        }
        if (_captureDir == null) return;

        Note("shim_version", "1");
        Note("started_utc", DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture));
        Note("command_line", Environment.CommandLine);
        Note("argument_tail", ArgumentTail(Environment.CommandLine));
        Note("cwd", Directory.GetCurrentDirectory());
        Note("real_engine", realExe);
        Note("real_engine_sha256", Sha256(realExe));
        Note("stdin_redirected", Console.IsInputRedirected.ToString());
        Note("stdout_redirected", Console.IsOutputRedirected.ToString());
        Note("parent_pid", ParentPid());
        string label = Environment.GetEnvironmentVariable("EZNEC_SPY_LABEL");
        if (!string.IsNullOrEmpty(label)) Note("label", label);

        SnapshotWatchedDirs("pre");
    }

    private static void EndCapture(string realExe, int exitCode, long elapsedMs)
    {
        if (_captureDir == null) return;
        Note("exit_code", exitCode.ToString(CultureInfo.InvariantCulture));
        Note("elapsed_ms", elapsedMs.ToString(CultureInfo.InvariantCulture));
        Note("finished_utc", DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture));
        SnapshotWatchedDirs("post");
        FlushMeta();
    }

    /// The two places the engine's file I/O can land: the working directory EZNEC
    /// chose, and the engine's own directory (where EZN5.NEC / NEC5.OUT live).
    private static IEnumerable<string> WatchedDirs(string realExe)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var d in new[] { Directory.GetCurrentDirectory(), Path.GetDirectoryName(realExe) })
            if (d != null && seen.Add(d) && Directory.Exists(d)) yield return d;
    }

    private static void SnapshotWatchedDirs(string phase)
    {
        string realExe;
        try { realExe = ResolveRealEngine(); } catch { return; }

        string outDir = Path.Combine(_captureDir, phase);
        Directory.CreateDirectory(outDir);
        var manifest = new StringBuilder();

        foreach (var dir in WatchedDirs(realExe))
        {
            manifest.AppendLine("# " + dir);
            string[] files;
            try { files = Directory.GetFiles(dir); } catch { continue; }
            foreach (var f in files)
            {
                FileInfo fi;
                try { fi = new FileInfo(f); } catch { continue; }
                bool copied = false;
                if (fi.Length <= MaxCopyBytes && !NoCopyExt.Contains(fi.Extension))
                {
                    try
                    {
                        File.Copy(f, Path.Combine(outDir, SafeName(dir, fi.Name)), true);
                        copied = true;
                    }
                    catch { }
                }
                manifest.AppendFormat(CultureInfo.InvariantCulture, "{0}\t{1}\t{2:o}\t{3}\t{4}\n",
                    fi.Name, fi.Length, fi.LastWriteTimeUtc, Sha256(f), copied ? "copied" : "manifest-only");
            }
        }
        try { File.WriteAllText(Path.Combine(_captureDir, phase + "-manifest.tsv"), manifest.ToString()); }
        catch { }
    }

    /// Watched dirs can collide on a basename; prefix with a short dir tag when they do.
    private static string SafeName(string dir, string name)
    {
        string tag = Path.GetFileName(dir.TrimEnd(Path.DirectorySeparatorChar));
        if (string.IsNullOrEmpty(tag)) tag = "root";
        foreach (char c in Path.GetInvalidFileNameChars()) tag = tag.Replace(c, '_');
        return tag + "__" + name;
    }

    private static string TeePath(string name)
    {
        return _captureDir == null ? null : Path.Combine(_captureDir, name);
    }

    private static void Note(string key, string value)
    {
        Meta.Append(key).Append('\t').Append((value ?? string.Empty).Replace("\r", " ").Replace("\n", " ")).Append('\n');
    }

    private static void FlushMeta()
    {
        if (_captureDir == null) return;
        try { File.WriteAllText(Path.Combine(_captureDir, "meta.tsv"), Meta.ToString()); } catch { }
    }

    private static string Sha256(string path)
    {
        try
        {
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "").ToLowerInvariant();
        }
        catch { return "-"; }
    }

    private static string ParentPid()
    {
        // Best-effort: WMI is the only portable route on .NET Framework and it is not
        // worth a dependency here. The command line + cwd already identify the caller.
        try { return Process.GetCurrentProcess().Id.ToString(CultureInfo.InvariantCulture) + " (self)"; }
        catch { return "-"; }
    }
}
