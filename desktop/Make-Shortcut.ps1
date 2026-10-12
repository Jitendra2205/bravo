# Puts a Bravo shortcut (puppy icon) on the Desktop and in the Start menu.
# Right-click either one and choose "Pin to taskbar" or "Pin to Start".
# Run-Bravo.cmd calls this on every start, so moving the Bravo folder fixes the shortcuts too.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# The shortcut carries the same app ID as Bravo's window, so a pinned icon and the running window
# show as one taskbar button.
$appIdCode = @'
using System;
using System.Runtime.InteropServices;
namespace BravoShortcut {
  [StructLayout(LayoutKind.Sequential, Pack = 4)]
  public struct PropertyKey { public Guid fmtid; public uint pid; }
  [StructLayout(LayoutKind.Explicit)]
  public struct PropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }
  [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IPropertyStore {
    void GetCount(out uint count);
    void GetAt(uint index, out PropertyKey key);
    void GetValue(ref PropertyKey key, out PropVariant value);
    void SetValue(ref PropertyKey key, ref PropVariant value);
    void Commit();
  }
  [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  public interface IPersistFile {
    void GetClassID(out Guid id);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string file, uint mode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string file, bool remember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string file);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string file);
  }
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")] public class ShellLink {}
  public static class Tool {
    public static void SetAppId(string lnk, string appId) {
      object link = new ShellLink();
      IPersistFile file = (IPersistFile)link;
      file.Load(lnk, 2);
      PropertyKey key = new PropertyKey();
      key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");   // PKEY_AppUserModel_ID
      key.pid = 5;
      PropVariant value = new PropVariant();
      value.vt = 31;                                                   // VT_LPWSTR
      value.p = Marshal.StringToCoTaskMemUni(appId);
      try { ((IPropertyStore)link).SetValue(ref key, ref value); ((IPropertyStore)link).Commit(); file.Save(lnk, true); }
      finally { Marshal.FreeCoTaskMem(value.p); }
    }
  }
}
'@

$shell = New-Object -ComObject WScript.Shell
$python = Join-Path $here '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $python)) { exit 0 }   # first run: the app isn't installed yet

foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  $path = Join-Path $folder 'Bravo.lnk'
  $lnk = $shell.CreateShortcut($path)
  $lnk.TargetPath = $python
  $lnk.Arguments = '"' + (Join-Path $here 'app.py') + '"'
  $lnk.WorkingDirectory = $here
  $lnk.IconLocation = (Join-Path $here 'ui\bravo.ico') + ',0'
  $lnk.Description = 'Bravo, your AI agent'
  $lnk.Save()
  try {
    if (-not ('BravoShortcut.Tool' -as [type])) { Add-Type -TypeDefinition $appIdCode }
    [BravoShortcut.Tool]::SetAppId($path, 'Bravo.Desktop')   # must match app.py
  } catch {
    # The shortcut still works; only taskbar grouping is affected.
  }
}
