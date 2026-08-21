using System;
using System.Diagnostics;
using System.Threading;

class SlowEngine
{
    static int Main(string[] args)
    {
        int ms = 2000;
        string env = Environment.GetEnvironmentVariable("SLOW_MS");
        if (env != null) int.TryParse(env, out ms);
        Thread.Sleep(ms);
        var psi = new ProcessStartInfo(@"C:\EZNEC 7.0\Docs\NEC5CL_x13.real.exe");
        string a = "";
        foreach (string s in args) a += "\"" + s + "\" ";
        psi.Arguments = a.Trim();
        psi.UseShellExecute = false;
        var p = Process.Start(psi);
        p.WaitForExit();
        return p.ExitCode;
    }
}
