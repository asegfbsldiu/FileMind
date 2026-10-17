; Compile from PowerShell with ISCC.exe /DAppVersion=0.1.0 packaging\FileMind.iss.
; Paths remain relative to this script; no teammate workstation paths are embedded.
; The pinned Simplified Chinese translation is shipped with this project.
#define ProjectRoot AddBackslash(SourcePath) + ".."
#ifndef AppVersion
  #if FileExists(ProjectRoot + "\build\release\metadata.iss")
    #include ProjectRoot + "\build\release\metadata.iss"
  #else
    #error "Run scripts/build-windows.ps1 -Stage Prepare to generate version metadata."
  #endif
#endif

#if !FileExists(ProjectRoot + "\dist\FileMind\FileMind.exe")
  #error "Run PyInstaller first: dist\FileMind\FileMind.exe was not found."
#endif

[Setup]
AppId={{0E87ED3D-E4CB-4F52-BE50-926B2373CB3F}
AppName=FileMind
AppVersion={#AppVersion}
AppPublisher=FileMind contributors
DefaultDirName={localappdata}\Programs\FileMind
DefaultGroupName=FileMind
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile={#ProjectRoot}\filemind\ui\assets\FileMind_AppIcon.ico
UninstallDisplayIcon={app}\FileMind.exe
LicenseFile={#ProjectRoot}\packaging\installer\LICENSE.zh-CN.txt
OutputDir={#ProjectRoot}\dist\installer
OutputBaseFilename=FileMind-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile={#ProjectRoot}\packaging\installer\wizard-sidebar.bmp
WizardSmallImageFile={#ProjectRoot}\packaging\installer\wizard-small.bmp
WizardImageStretch=yes
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=yes
DisableFinishedPage=no
ShowLanguageDialog=no
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "{#ProjectRoot}\packaging\installer\languages\ChineseSimplified.isl"

[LangOptions]
DialogFontName=Microsoft YaHei UI
DialogFontSize=9
WelcomeFontName=Microsoft YaHei UI
WelcomeFontSize=12

[Messages]
SetupWindowTitle=%1 安装
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=这个向导将引导你完成 [name] 的安装过程。%n%n在开始安装之前，建议先关闭其他应用程序。%n%n点击“下一步”继续。
WizardLicense=许可协议
LicenseLabel=在安装 [name] 之前，请阅读许可说明。
LicenseLabel3=请阅读下面的开源许可说明。点击“我同意”后继续安装。
WizardSelectDir=选择安装位置
SelectDirDesc=选择 [name] 的安装文件夹。
SelectDirLabel3=安装程序将把 [name] 安装到以下文件夹。
SelectDirBrowseLabel=要安装到其他位置，请点击“浏览”选择文件夹。点击“下一步”继续。
WizardSelectTasks=选择附加任务
SelectTasksDesc=选择你希望安装程序执行的附加任务。
SelectTasksLabel2=勾选需要的选项，点击“安装”开始安装 [name]。
WizardInstalling=正在安装
InstallingLabel=请稍候，安装向导正在安装 [name]。
StatusExtractFiles=正在复制文件...
FinishedHeadingLabel=正在完成 [name] 安装向导
FinishedLabelNoIcons=[name] 已成功安装到你的电脑上。
FinishedLabel=[name] 已成功安装到你的电脑上。
ClickFinish=点击“完成”关闭安装向导。

[CustomMessages]
AcceptLicenseButton=我同意(&I)
LicenseContinueHint=点击“我同意”表示接受上述许可条款并继续安装。你也可以点击“取消”退出。
DesktopShortcut=创建桌面快捷方式(&D)
ShortcutGroup=附加快捷方式：
StartupShortcut=开机自动启动 FileMind（可选）
StartupGroup=其他选项：
LaunchFileMind=启动 FileMind

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:ShortcutGroup}"
Name: "startup"; Description: "{cm:StartupShortcut}"; GroupDescription: "{cm:StartupGroup}"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\FileMind\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\FileMind"; Filename: "{app}\FileMind.exe"; WorkingDir: "{app}"; IconFilename: "{app}\FileMind.exe"; AppUserModelID: "FileMind.Desktop"
Name: "{autodesktop}\FileMind"; Filename: "{app}\FileMind.exe"; WorkingDir: "{app}"; IconFilename: "{app}\FileMind.exe"; AppUserModelID: "FileMind.Desktop"; Tasks: desktopicon
Name: "{userstartup}\FileMind"; Filename: "{app}\FileMind.exe"; WorkingDir: "{app}"; IconFilename: "{app}\FileMind.exe"; AppUserModelID: "FileMind.Desktop"; Tasks: startup

[InstallDelete]
Type: files; Name: "{userstartup}\FileMind.lnk"; Tasks: not startup
Type: files; Name: "{autodesktop}\FileMind.lnk"; Tasks: not desktopicon

[Run]
Filename: "{app}\FileMind.exe"; Description: "{cm:LaunchFileMind}"; Flags: nowait postinstall skipifsilent

[Code]
procedure InitializeWizard;
var
  LicenseHint: TNewStaticText;
begin
  WizardForm.LicenseAcceptedRadio.Visible := False;
  WizardForm.LicenseNotAcceptedRadio.Visible := False;
  LicenseHint := TNewStaticText.Create(WizardForm);
  LicenseHint.Parent := WizardForm.LicensePage;
  LicenseHint.AutoSize := False;
  LicenseHint.WordWrap := True;
  LicenseHint.SetBounds(WizardForm.LicenseMemo.Left,
    WizardForm.LicenseAcceptedRadio.Top, WizardForm.LicenseMemo.Width, ScaleY(34));
  LicenseHint.Caption := CustomMessage('LicenseContinueHint');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpLicense then
  begin
    { Consent is expressed by clicking the explicitly labelled I agree button. }
    WizardForm.LicenseAcceptedRadio.Checked := True;
    WizardForm.NextButton.Caption := CustomMessage('AcceptLicenseButton');
  end
  else if CurPageID = wpSelectTasks then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall)
  else if CurPageID <> wpFinished then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonNext);
end;
