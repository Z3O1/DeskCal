// Transparent WebView2 child of the original DeskCal canvas. No HTTP listener.
using System;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;

static class CardHost
{
    const string Origin = "https://deskcal.invalid/";
    static Control dispatcher;
    static CoreWebView2Environment env;
    static CoreWebView2Controller view;
    static Rectangle bounds;
    static bool visible, loaded, browserExited;
    static string pending, media, assets, document;
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] static extern bool InvalidateRect(IntPtr hwnd, IntPtr rect, bool erase);
    static IntPtr parent;

    static void Emit(string text) { Console.WriteLine(text); Console.Out.Flush(); }

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length != 4) return 2;
        try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch (EntryPointNotFoundException) { }
        parent = new IntPtr(long.Parse(args[0], CultureInfo.InvariantCulture));
        document = Path.GetFullPath(args[1]);
        assets = Path.GetFullPath(args[2]);
        Environment.SetEnvironmentVariable("WEBVIEW2_DEFAULT_BACKGROUND_COLOR", "00000000");
        Console.OutputEncoding = new UTF8Encoding(false);
        dispatcher = new Control();
        var handle = dispatcher.Handle;
        new Thread(Read) { IsBackground = true }.Start();
        dispatcher.BeginInvoke((Action)(() => Start(args[3])));
        Application.Run();
        if (view != null) view.Close();
        // Closing the controller is asynchronous in the browser process. Pump its
        // exit notification before returning so temporary profiles are not locked.
        var deadline = DateTime.UtcNow.AddSeconds(8);
        while (env != null && !browserExited && DateTime.UtcNow < deadline)
        {
            Application.DoEvents();
            Thread.Sleep(20);
        }
        return 0;
    }

    static async void Start(string profile)
    {
        try
        {
            env = await CoreWebView2Environment.CreateAsync(null, profile);
            env.BrowserProcessExited += (s, e) => { browserExited = true; };
            view = await env.CreateCoreWebView2ControllerAsync(parent);
            view.DefaultBackgroundColor = Color.Transparent;
            view.BoundsMode = CoreWebView2BoundsMode.UseRawPixels;
            var core = view.CoreWebView2;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.AreHostObjectsAllowed = false;
            core.Settings.AreBrowserAcceleratorKeysEnabled = false;
            core.NewWindowRequested += (s, e) => { e.Handled = true; };
            core.NavigationStarting += (s, e) => { if (e.Uri.Split('#')[0] != Origin + "card.html") e.Cancel = true; };
            core.WebMessageReceived += (s, e) => {
                if (e.Source == Origin + "card.html") Emit("msg " + e.WebMessageAsJson);
            };
            core.AddWebResourceRequestedFilter(Origin + "*", CoreWebView2WebResourceContext.All);
            core.WebResourceRequested += Resource;
            core.NavigationCompleted += (s, e) => {
                if (!e.IsSuccess) { Emit("error " + e.WebErrorStatus); return; }
                loaded = true;
                if (pending != null) core.PostWebMessageAsJson(pending);
                Emit("ready");
            };
            core.ProcessFailed += (s, e) => Emit("error " + e.ProcessFailedKind);
            Place();
            core.Navigate(Origin + "card.html");
        }
        catch (Exception ex) { Emit("error " + ex.GetType().Name); Application.ExitThread(); }
    }

    static string Under(string root, string relative)
    {
        if (String.IsNullOrEmpty(root) || relative.IndexOf('\0') >= 0) return null;
        var start = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var path = Path.GetFullPath(Path.Combine(start, relative.Replace('/', Path.DirectorySeparatorChar)));
        return path.StartsWith(start, StringComparison.OrdinalIgnoreCase) ? path : null;
    }

    static string Mime(string path)
    {
        switch (Path.GetExtension(path).ToLowerInvariant())
        {
            case ".html": case ".htm": return "text/html; charset=utf-8";
            case ".css": return "text/css; charset=utf-8";
            case ".js": return "text/javascript; charset=utf-8";
            case ".json": return "application/json";
            case ".svg": return "image/svg+xml";
            case ".png": return "image/png";
            case ".jpg": case ".jpeg": return "image/jpeg";
            case ".gif": return "image/gif";
            case ".webp": return "image/webp";
            case ".woff": return "font/woff";
            case ".woff2": return "font/woff2";
            case ".ttf": return "font/ttf";
            case ".otf": return "font/otf";
            case ".mp3": return "audio/mpeg";
            case ".wav": return "audio/wav";
            case ".ogg": return "audio/ogg";
            case ".mp4": return "video/mp4";
            default: return "application/octet-stream";
        }
    }

    static void Resource(object sender, CoreWebView2WebResourceRequestedEventArgs e)
    {
        try
        {
            var uri = new Uri(e.Request.Uri);
            var path = Uri.UnescapeDataString(uri.AbsolutePath);
            string file = null;
            if (path == "/card.html") file = document;
            else if (path.StartsWith("/_anki/")) file = Under(assets, path.Substring(7));
            else if (path.StartsWith("/media/")) file = Under(media, path.Substring(7));
            if (file == null || !File.Exists(file) || e.Request.Method != "GET")
            {
                e.Response = env.CreateWebResourceResponse(null, 404, "Not Found", "");
                return;
            }
            e.Response = env.CreateWebResourceResponse(new MemoryStream(File.ReadAllBytes(file)), 200, "OK",
                "Content-Type: " + Mime(file) + "\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff");
        }
        catch (Exception) { e.Response = env.CreateWebResourceResponse(null, 404, "Not Found", ""); }
    }

    static void Read()
    {
        try
        {
            string line;
            while ((line = Console.ReadLine()) != null)
            {
                var copy = line;
                dispatcher.BeginInvoke((Action)(() => Command(copy)));
            }
            dispatcher.BeginInvoke((Action)Application.ExitThread);
        }
        catch (InvalidOperationException) { }
    }

    static void Place()
    {
        if (view == null) return;
        view.Bounds = bounds;
        view.IsVisible = visible && !bounds.IsEmpty;
        view.NotifyParentWindowPositionChanged();
    }

    static async void Command(string line)
    {
        try
        {
            if (line.StartsWith("card "))
            {
                pending = line.Substring(5);
                InvalidateRect(parent, IntPtr.Zero, false);
                if (loaded) view.CoreWebView2.PostWebMessageAsJson(pending);
            }
            else if (line.StartsWith("media "))
                media = Encoding.UTF8.GetString(Convert.FromBase64String(line.Substring(6)));
            else if (line == "activate" && loaded && visible)
                await view.CoreWebView2.ExecuteScriptAsync("window.deskcalActivate?.()");
            else if (line == "moved" && view != null) view.NotifyParentWindowPositionChanged();
            else if (line.StartsWith("bounds "))
            {
                var p = line.Split(' ');
                bounds = new Rectangle(int.Parse(p[1]), int.Parse(p[2]), int.Parse(p[3]), int.Parse(p[4]));
                visible = p[5] == "1";
                Place();
            }
        }
        catch (Exception ex) { Emit("error " + ex.GetType().Name); }
    }
}
