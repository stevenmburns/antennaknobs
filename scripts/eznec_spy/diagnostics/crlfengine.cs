using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class CrlfEngine
{
    static int Main(string[] args)
    {
        var psi = new ProcessStartInfo(@"C:\EZNEC 7.0\Docs\momwire_real.exe");
        string a = "";
        foreach (string s in args) a += "\"" + s + "\" ";
        psi.Arguments = a.Trim();
        psi.UseShellExecute = false;
        var p = Process.Start(psi);
        p.WaitForExit();

        if (args.Length >= 2)
        {
            string outPath = Path.Combine(Directory.GetCurrentDirectory(), args[1]);
            if (File.Exists(outPath))
            {
                byte[] raw = File.ReadAllBytes(outPath);
                var sb = new MemoryStream();
                for (int i = 0; i < raw.Length; i++)
                {
                    bool prevCr = (i > 0 && raw[i - 1] == 13);
                    if (raw[i] == 10 && !prevCr) sb.WriteByte(13);
                    sb.WriteByte(raw[i]);
                }
                File.WriteAllBytes(outPath, sb.ToArray());
                File.AppendAllText(@"C:\EZNEC 7.0\Docs\engine_probe.log",
                    "CRLF fixup " + DateTime.Now.ToString("HH:mm:ss") + " : " +
                    raw.Length + " -> " + sb.Length + " bytes\r\n");
            }
        }
        return p.ExitCode;
    }
}
