using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class LogEngine
{
    static int Main(string[] args)
    {
        string log = @"C:\EZNEC 7.0\Docs\engine_probe.log";
        var sb = new StringBuilder();
        sb.AppendLine("=== invocation " + DateTime.Now.ToString("HH:mm:ss.fff") + " ===");
        sb.AppendLine("cwd      : " + Directory.GetCurrentDirectory());
        sb.AppendLine("cmdline  : " + Environment.CommandLine);
        sb.AppendLine("argc     : " + args.Length);
        for (int i = 0; i < args.Length; i++)
            sb.AppendLine("  arg[" + i + "] : " + args[i]);
        foreach (string f in new string[] { "EZN5.NEC", "NEC.IN", "NEC5.OUT", "NEC.OUT" })
        {
            string p = Path.Combine(Directory.GetCurrentDirectory(), f);
            sb.AppendLine("  before " + f + " : " + (File.Exists(p) ? new FileInfo(p).Length + " B" : "absent"));
        }
        var psi = new ProcessStartInfo(@"C:\EZNEC 7.0\Docs\momwire_real.exe");
        string a = "";
        foreach (string s in args) a += "\"" + s + "\" ";
        psi.Arguments = a.Trim();
        psi.UseShellExecute = false;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        var sw = Stopwatch.StartNew();
        var p2 = Process.Start(psi);
        string so = p2.StandardOutput.ReadToEnd();
        string se = p2.StandardError.ReadToEnd();
        p2.WaitForExit();
        sw.Stop();
        sb.AppendLine("exit     : " + p2.ExitCode + " in " + sw.ElapsedMilliseconds + " ms");
        sb.AppendLine("stdout   : " + (so.Length > 200 ? so.Substring(0, 200) : so).Replace("\r\n", " | "));
        sb.AppendLine("stderr   : " + (se.Length > 200 ? se.Substring(0, 200) : se).Replace("\r\n", " | "));
        foreach (string f in new string[] { "EZN5.NEC", "NEC.IN", "NEC5.OUT", "NEC.OUT" })
        {
            string p = Path.Combine(Directory.GetCurrentDirectory(), f);
            sb.AppendLine("  after  " + f + " : " + (File.Exists(p) ? new FileInfo(p).Length + " B" : "absent"));
        }
        File.AppendAllText(log, sb.ToString());
        return p2.ExitCode;
    }
}
