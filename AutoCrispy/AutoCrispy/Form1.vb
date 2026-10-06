Imports System.IO
Imports System.Reflection

Public Class Form1

#Region "VARS"

    Dim Root As String = Application.StartupPath
    Dim AppData As String = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
    Dim WaitScale As Integer = 0
    Dim SettingsLoc As Point = New Point(240, 166)
    Dim LoadedSettings As FormSettings.Settings
    Dim SkipList As New List(Of String)

    Const HotToggle As String = "%`"

    Public Property ChainControl As DragDropList
    Public Property ChainList As New List(Of FormSettings.ChainObject)
    Public Property ChainThumbs As New List(Of Image)
    Public Property CaffePath As String
    Public Property WaifuNcnnPath As String
    Public Property RealSRNcnnPath As String
    Public Property RealESRGNcnnPath As String
    Public Property SRMDNcnnPath As String
    Public Property WaifuCppPath As String
    Public Property Anime4kPath As String
    Public Property TexConvPath As String
    Public Property xBRZPath As String
    Public Property PyPath As String
    Public Property PyModels As New List(Of String)

#End Region

#Region "Structs"

    <Serializable()> Public Structure ArguementString
        Private Property Arguements As String
        Public Function GetArguements() As String
            Return System.Text.RegularExpressions.Regex.Replace(Arguements, " {2,}", " ").Trim
        End Function
        Public Sub AddArguement(Flag As String)
            Arguements += " " & Flag
        End Sub
        Public Sub AddArguement(Flag As String, Value As String)
            Arguements += " " & Flag & " " & Value
        End Sub
        Public Sub AddArguement(Flag As String, Enabled As Boolean)
            If Enabled Then Arguements += " " & Flag
        End Sub
    End Structure

#End Region

#Region "Loading"

    Private Sub Form1_Load(sender As Object, e As EventArgs) Handles MyBase.Load
        Me.Size = New Size(660, 413)
        Me.SetStyle(ControlStyles.OptimizedDoubleBuffer, True)
        Application.CurrentCulture = New Globalization.CultureInfo("EN-US")
        PreloadImageList()
        ChainControl = New DragDropList(ChainPreview, 7)
        AddHandler ChainControl.OrderChanged, AddressOf ChainControl_OrderChanged

        If ExeTextBox.Text <> "" Then
            Root = ExeTextBox.Text
        End If
        StartUpCheckEXE()

        Try
            If File.Exists(Root & "\portable.xml") Then
                FormSettings.LoadSettings(Me, Deserialize(Of FormSettings.Settings)(File.ReadAllText(Root & "\portable.xml")))
            ElseIf File.Exists(AppData & "\AutoCrispy\settings.xml") Then
                FormSettings.LoadSettings(Me, Deserialize(Of FormSettings.Settings)(File.ReadAllText(AppData & "\AutoCrispy\settings.xml")))
            Else
                FormSettings.LoadSettings(Me, Deserialize(Of FormSettings.Settings)(My.Resources.default_settings))
                If Not Directory.Exists(AppData & "\AutoCrispy") Then
                    Directory.CreateDirectory(AppData & "\AutoCrispy")
                End If
            End If
        Catch ex As Exception
            MsgBox("Failed to load Settings!  Loading program defaults.")
            FormSettings.LoadSettings(Me, Deserialize(Of FormSettings.Settings)(My.Resources.default_settings))
        End Try

        If ExeComboBox.Items.Count > 0 AndAlso ExeComboBox.SelectedIndex = -1 Then
            ExeComboBox.SelectedIndex = 0
            SetSettingsWindow()
        ElseIf ExeComboBox.SelectedIndex >= 0 Then
            SetSettingsWindow()
        End If

        ChainControl.DrawList(ChainControl.ListItems)
        WatchDogButton.Select()
        If Environment.GetCommandLineArgs.Count > 1 Then
            WatchDogButton_Click(sender, e)
        End If
    End Sub

    Private Sub Form1_Closing(sender As Object, e As EventArgs) Handles MyBase.Closing
        If PortableCheckBox.Checked = True Then
            File.WriteAllText(Root & "\portable.xml", Serialize(New FormSettings.Settings(Me)))
        Else
            File.WriteAllText(AppData & "\AutoCrispy\settings.xml", Serialize(New FormSettings.Settings(Me)))
        End If
    End Sub

    Private Sub StartUpCheckEXE()
        Dim RootFolders As List(Of String) = Directory.GetDirectories(Root).ToList
        RootFolders.Add(Root)
        ExeComboBox.Items.Clear()
        For Each Folder As String In RootFolders
            AddEXE(Folder, "\waifu2x-caffe-cui.exe", "Waifu2x Caffe", CaffePath)
            AddEXE(Folder, "\waifu2x-ncnn-vulkan.exe", "Waifu2x Vulkan", WaifuNcnnPath)
            AddEXE(Folder, "\realsr-ncnn-vulkan.exe", "RealSR Vulkan", RealSRNcnnPath)
            AddEXE(Folder, "\realesrgan-ncnn-vulkan.exe", "RealESRGAN Vulkan", RealESRGNcnnPath)
            AddEXE(Folder, "\srmd-ncnn-vulkan.exe", "SRMD Vulkan", SRMDNcnnPath)
            AddEXE(Folder, "\waifu2x-converter-cpp.exe", "Waifu2x CPP", WaifuCppPath)
            AddEXE(Folder, "\Anime4KCPP_CLI.exe", "Anime4k CPP", Anime4kPath)
            AddEXE(Folder, "\texconv.exe", "TexConv", TexConvPath)
            AddEXE(Folder, "\ScalerTest_Windows.exe", "xBRZ", xBRZPath)
            If File.Exists(Folder & "\esrgan.exe") Then
                PyModels.Clear()
                PyModel.Items.Clear()
                ExeComboBox.Items.Add("ESRGAN")
                PyPath = "\" & IIf(Folder <> Root, Path.GetFileName(Folder), "") & "\esrgan.exe"
                For Each SubFolder As String In Directory.GetDirectories(Folder)
                    Dim Models As String() = Directory.EnumerateFiles(SubFolder, "*.pth").ToArray
                    For Each PythonModel As String In Models
                        PyModels.Add(PythonModel)
                        PyModel.Items.Add(Path.GetFileName(PythonModel))
                    Next
                Next
                If PyModels.Count > 0 Then
                    PyModel.SelectedIndex = 0
                Else
                    MsgBox("No ESRGAN Models Found!", MsgBoxStyle.Critical)
                End If
            End If
        Next
    End Sub

    Private Sub AddEXE(Source As String, ExeName As String, ModelName As String, ByRef ModelPath As String)
        If File.Exists(Source & ExeName) Then
            ExeComboBox.Items.Add(ModelName)
            ModelPath = "\" & IIf(Source <> Root, Path.GetFileName(Source), "") & ExeName
        End If
    End Sub

    Private Sub PreloadImageList()
        ChainThumbs.Add(My.Resources._0)
        ChainThumbs.Add(My.Resources._1)
        ChainThumbs.Add(My.Resources._2)
        ChainThumbs.Add(My.Resources._3)
        ChainThumbs.Add(My.Resources._4)
        ChainThumbs.Add(My.Resources._5)
        ChainThumbs.Add(My.Resources._6)
        ChainThumbs.Add(My.Resources._7)
        ChainThumbs.Add(My.Resources._8)
    End Sub

#End Region

#Region "UI"

    Private Sub ExeComboBox_SelectedIndexChanged(sender As Object, e As EventArgs) Handles ExeComboBox.SelectedIndexChanged
        SetSettingsWindow()
    End Sub

    Private Sub InputBrowse_Click(sender As Object, e As EventArgs) Handles InputBrowse.Click
        InputTextBox.Text = GetFolder()
    End Sub

    Private Sub OutputBrowse_Click(sender As Object, e As EventArgs) Handles OutputBrowse.Click
        OutputTextBox.Text = GetFolder()
    End Sub

    Private Sub ExeBrowse_Click(sender As Object, e As EventArgs) Handles ExeBrowse.Click
        ExeTextBox.Text = GetFolder()
    End Sub

    Private Sub ExeTextBox_TextChanged(sender As Object, e As EventArgs) Handles ExeTextBox.TextChanged
        If Directory.Exists(ExeTextBox.Text) = True Then
            Root = ExeTextBox.Text
        Else
            Root = Application.StartupPath
        End If
        StartUpCheckEXE()
        If ExeComboBox.Items.Count > 0 Then
            ExeComboBox.SelectedIndex = 0
            SetSettingsWindow()
        End If
    End Sub

    Private Sub DefringeCheck_CheckedChanged(sender As Object, e As EventArgs) Handles DefringeCheck.CheckedChanged
        DefringeThresh.Enabled = DefringeCheck.Checked
    End Sub

    Private Sub ChainSave_Click(sender As Object, e As EventArgs) Handles ChainSave.Click
        Using SFD As New SaveFileDialog With {.Filter = "XML Files|*.xml|All Files|*.*"}
            If SFD.ShowDialog = DialogResult.OK Then
                File.WriteAllText(SFD.FileName, Serialize(ChainList))
            End If
        End Using
    End Sub

    Private Sub ChainLoad_Click(sender As Object, e As EventArgs) Handles ChainLoad.Click
        Using OFD As New OpenFileDialog With {.Filter = "XML Files|*.xml|All Files|*.*"}
            If OFD.ShowDialog = DialogResult.OK Then
                ChainControl.ListItems.Clear()
                ChainList.Clear()
                Dim LoadedChain = Deserialize(Of List(Of FormSettings.ChainObject))(File.ReadAllText(OFD.FileName))
                If LoadedChain IsNot Nothing Then
                    ChainList = LoadedChain
                End If
                For i = 0 To ChainList.Count - 1
                    Dim ChainItem As FormSettings.ChainObject = ChainList(i)
                    Dim IconIdx As Integer = Math.Max(0, Math.Min(ChainItem.IconIndex, ChainThumbs.Count - 1))
                    Dim Thumb As Image = If(ChainThumbs.Count > 0, ChainThumbs.Item(IconIdx), Nothing)
                    ChainControl.ListItems.Add(New DragDropList.DragDropItem(i, ChainItem.Name, Thumb))
                Next
                ChainControl.DrawList(ChainControl.ListItems)
            End If
        End Using
    End Sub

    Private Sub ChainAdd_Click(sender As Object, e As EventArgs) Handles ChainAdd.Click
        If ExeComboBox.SelectedItem IsNot Nothing Then
            AddModelToChain(ExeComboBox.SelectedItem.ToString())
        End If
    End Sub

    Private Sub ChainRemove_Click(sender As Object, e As EventArgs) Handles ChainRemove.Click
        If ChainList.Count > 0 Then
            Dim RemoveIdx As Integer = ChainControl.GetCurrentIndex()
            If RemoveIdx < 0 OrElse RemoveIdx >= ChainList.Count Then
                RemoveIdx = ChainList.Count - 1
            End If
            ChainList.RemoveAt(RemoveIdx)
            If RemoveIdx < ChainControl.ListItems.Count Then
                ChainControl.ListItems.RemoveAt(RemoveIdx)
            End If
            ChainControl.ReorderList()
            ChainControl.DrawList(ChainControl.ListItems)
        End If
    End Sub

    Private Sub RemoveItemFromChain(sender As Object, e As EventArgs) Handles ChainContextDelete.Click
        Dim RemoveIdx As Integer = ChainControl.GetCurrentIndex()
        If RemoveIdx >= 0 AndAlso RemoveIdx < ChainList.Count Then
            ChainList.RemoveAt(RemoveIdx)
            If RemoveIdx < ChainControl.ListItems.Count Then
                ChainControl.ListItems.RemoveAt(RemoveIdx)
            End If
            ChainControl.ReorderList()
            ChainControl.DrawList(ChainControl.ListItems)
        End If
    End Sub

    Private Sub ChainContextEdit_Click(sender As Object, e As EventArgs) Handles ChainContextEdit.Click
        Dim ItemIndex As Integer = ChainControl.GetCurrentIndex()
        If ItemIndex >= 0 AndAlso ItemIndex < ChainList.Count Then
            Using ECD As New EditChainDialog(Serialize(ChainList(ItemIndex)))
                If ECD.ShowDialog = DialogResult.OK Then
                    Try
                        Dim NewChainItem As FormSettings.ChainObject = Deserialize(Of FormSettings.ChainObject)(ECD.ResultText)
                        ChainList(ItemIndex) = NewChainItem
                        If ItemIndex < ChainControl.ListItems.Count Then
                            Dim IconIdx As Integer = Math.Max(0, Math.Min(NewChainItem.IconIndex, ChainThumbs.Count - 1))
                            Dim Thumb As Image = If(ChainThumbs.Count > 0, ChainThumbs.Item(IconIdx), Nothing)
                            ChainControl.ListItems(ItemIndex) = New DragDropList.DragDropItem(ItemIndex, NewChainItem.Name, Thumb)
                            ChainControl.DrawList(ChainControl.ListItems)
                        End If
                    Catch ex As Exception
                        MsgBox("Error: New settings could not be parsed.")
                    End Try
                End If
            End Using
        End If
    End Sub

    Private Sub ChainControl_OrderChanged(OldIndices As List(Of Integer))
        Dim TempList As New List(Of FormSettings.ChainObject)
        For Each OldIdx As Integer In OldIndices
            If OldIdx >= 0 AndAlso OldIdx < ChainList.Count Then
                TempList.Add(ChainList(OldIdx))
            End If
        Next
        ChainList = TempList
    End Sub

    Private Sub DDxFormatListBox_SelectedIndexChanged(sender As Object, e As EventArgs) Handles DDxFormatListBox.SelectedIndexChanged
        DDxFormatLabel.Text = "Format: " & DDxFormatListBox.SelectedItem
    End Sub

    Private Sub DDxModeBox_SelectedIndexChanged(sender As Object, e As EventArgs) Handles DDxModeBox.SelectedIndexChanged
        Select Case DDxModeBox.SelectedIndex
            Case 0
                DDxConvFormat.Enabled = True
            Case 1
                DDxConvFormat.Enabled = False
        End Select
    End Sub

    Private Sub RunOnceButton_Click(sender As Object, e As EventArgs) Handles RunOnceButton.Click
        Using OFD As New OpenFileDialog With {.Filter = "Image Files|*.png;*.jpg;*.bmp"}
            If OFD.ShowDialog = DialogResult.OK Then
                Using SFD As New SaveFileDialog With {.Filter = "PNG Images|*.png"}
                    If SFD.ShowDialog = DialogResult.OK Then
                        Dim TempPath As String = Path.GetTempPath & "Single_0"
                        If Directory.Exists(TempPath) Then Directory.Delete(TempPath, True)
                        Directory.CreateDirectory(TempPath)
                        File.Copy(OFD.FileName, TempPath & "\" & Path.GetFileName(SFD.FileName), True)
                        LoadedSettings = New FormSettings.Settings(Me)
                        LoadedSettings.Paths = New FormSettings.ProgramPaths(TempPath, Directory.GetParent(SFD.FileName).FullName, Root)
                        SwitchGroups(False)
                        WorkHorse.RunWorkerAsync()
                    End If
                End Using
            End If
        End Using
    End Sub

    Private Sub WatchDogButton_Click(sender As Object, e As EventArgs) Handles WatchDogButton.Click
        If (Not (Directory.Exists(InputTextBox.Text) = True)) OrElse (Not (Directory.Exists(OutputTextBox.Text) = True)) Then
            MsgBox("No path specified, or path invalid!", MsgBoxStyle.Critical, "Error")
        ElseIf WorkHorse.IsBusy = True Then
            WatchDogButton.Enabled = False
            WorkHorse.CancelAsync()
            SkipList.Clear()
        Else
            WatchDog.Enabled = Not WatchDog.Enabled
            WatchDogButton.Text = "Running: " & WatchDog.Enabled
            SwitchGroups(Not WatchDog.Enabled)
        End If
    End Sub

    Private Sub ThreadComboBox_SelectedIndexChanged(sender As Object, e As EventArgs) Handles ThreadComboBox.SelectedIndexChanged
        If ThreadComboBox.SelectedIndex = 1 Then
            NumericThreads.Enabled = True
        Else
            NumericThreads.Enabled = False
        End If
    End Sub

    Private Sub SeamsBox_SelectedIndexChanged(sender As Object, e As EventArgs) Handles SeamsBox.SelectedIndexChanged
        If SeamsBox.SelectedIndex > 0 Then
            SeamScale.Enabled = True
            SeamMargin.Enabled = True
        Else
            SeamScale.Enabled = False
            SeamMargin.Enabled = False
        End If
    End Sub

    Private Sub Anime4kCheck_Changes(sender As Object, e As EventArgs) Handles MyBase.Load, AnimeCppPre.CheckedChanged, AnimeCppPreFilter.CheckedChanged, AnimeCppPost.CheckedChanged, AnimeCppPostFilter.CheckedChanged, AnimeCPPCnn.CheckedChanged
        If AnimeCPPCnn.Checked = True Then
            AnimeCppPre.Checked = False
            AnimeCppPost.Checked = False
        End If
        AnimeCppPreFilter.Enabled = AnimeCppPre.Checked
        AnimeCppPreFilters.Enabled = AnimeCppPreFilter.Checked
        If AnimeCppPre.Checked = False Then AnimeCppPreFilter.Checked = False
        AnimeCppPostFilter.Enabled = AnimeCppPost.Checked
        AnimeCppPostFilters.Enabled = AnimeCppPostFilter.Checked
        If AnimeCppPost.Checked = False Then AnimeCppPostFilter.Checked = False
    End Sub

    Private Sub SetSettingsWindow()
        CaffeGroup.Visible = False
        VulkanGroup.Visible = False
        WaifuCPPGroup.Visible = False
        AnimeCPPGroup.Visible = False
        DDxGroup.Visible = False
        xBRZGroup.Visible = False
        PyGroup.Visible = False
        VulkanNoise.Enabled = True
        Select Case ExeComboBox.SelectedItem
            Case "Waifu2x Caffe"
                MoveShowGroup(CaffeGroup)
            Case "Waifu2x Vulkan"
                MoveShowGroup(VulkanGroup)
                VulkanScale.Value = 2
                VulkanScale.Enabled = True
            Case "RealSR Vulkan", "RealESRGAN Vulkan"
                MoveShowGroup(VulkanGroup)
                VulkanScale.Value = 4
                VulkanScale.Enabled = False
                VulkanNoise.Enabled = False
            Case "SRMD Vulkan"
                MoveShowGroup(VulkanGroup)
                VulkanScale.Value = 4
                VulkanScale.Enabled = False
            Case "Waifu2x CPP"
                MoveShowGroup(WaifuCPPGroup)
            Case "Anime4k CPP"
                MoveShowGroup(AnimeCPPGroup)
            Case "TexConv"
                MoveShowGroup(DDxGroup)
            Case "xBRZ"
                MoveShowGroup(xBRZGroup)
            Case "ESRGAN"
                MoveShowGroup(PyGroup)
        End Select
    End Sub

    Sub MoveShowGroup(ByRef Source As GroupBox)
        Source.Location = SettingsLoc
        Source.Visible = True
    End Sub

    Private Sub SwitchGroups(Enabled As Boolean)
        TabGroup.Enabled = Enabled
        SettingsGroup.Enabled = Enabled
        CaffeGroup.Enabled = Enabled
        VulkanGroup.Enabled = Enabled
        WaifuCPPGroup.Enabled = Enabled
        AnimeCPPGroup.Enabled = Enabled
        DDxGroup.Enabled = Enabled
        PyGroup.Enabled = Enabled
    End Sub

#End Region

#Region "Background"

    Private Sub WatchDog_Tick(sender As Object, e As EventArgs) Handles WatchDog.Tick
        If Not Directory.Exists(InputTextBox.Text) OrElse Not Directory.Exists(OutputTextBox.Text) Then Exit Sub
        Dim Source = Directory.GetFiles(InputTextBox.Text, "*.*", SearchOption.AllDirectories).Count
        Dim FileCheck = GetMissingFiles(InputTextBox.Text, OutputTextBox.Text).Count
        If Source = 0 OrElse FileCheck = 0 Then
            WaitScale = Math.Min(WaitScale + 1, 100)
            WatchDog.Interval = 1000 + (WaitScale * 590)
        Else
            WaitScale = 0
            WatchDog.Interval = 1000
            LoadedSettings = New FormSettings.Settings(Me)
            WorkHorse.RunWorkerAsync()
        End If
    End Sub

    Private Sub WorkHorse_DoWork(sender As Object, e As System.ComponentModel.DoWorkEventArgs) Handles WorkHorse.DoWork
        WatchDog.Stop()
        MakeUpscale()
        If WorkHorse.CancellationPending = True Then
            e.Cancel = True
        End If
    End Sub

    Private Sub WorkHorse_ProgressChanged(sender As Object, e As System.ComponentModel.ProgressChangedEventArgs) Handles WorkHorse.ProgressChanged
        UpscaleProgress.Value = e.ProgressPercentage
        If (HotKeyCheckbox.Checked = True) AndAlso (GetActiveWindow <> Me.Handle) Then
            SendKeys.Send(HotToggle)
            Threading.Thread.Sleep(200)
            SendKeys.Send(HotToggle)
        End If
    End Sub

    Private Sub WorkHorse_RunWorkerCompleted(sender As Object, e As System.ComponentModel.RunWorkerCompletedEventArgs) Handles WorkHorse.RunWorkerCompleted
        UpscaleProgress.Value = 0
        If e.Cancelled = True Then
            WatchDog.Enabled = False
            WatchDogButton.Text = "Running: " & False
            SwitchGroups(Not WatchDog.Enabled)
            WatchDogButton.Enabled = True
            Exit Sub
        End If
        If WatchDogButton.Text = "Running: True" Then
            WatchDog.Start()
        Else
            Dim SingleDir As String = Path.GetTempPath & "Single_0"
            If Directory.Exists(SingleDir) Then Directory.Delete(SingleDir, True)
            SwitchGroups(True)
        End If
    End Sub

#End Region

#Region "Upscale Routine"

    Private Sub MakeUpscale()
        Dim ActiveChain As List(Of FormSettings.ChainObject)
        If ChainList IsNot Nothing AndAlso ChainList.Count > 0 Then
            ActiveChain = New List(Of FormSettings.ChainObject)(ChainList)
        Else
            ActiveChain = New List(Of FormSettings.ChainObject)
            Dim SingleModel As FormSettings.ChainObject = GetCurrentBackendChainObject()
            If SingleModel.PackageType IsNot Nothing Then
                ActiveChain.Add(SingleModel)
            End If
        End If

        If ActiveChain.Count = 0 Then Exit Sub

        Dim TempPath As String = GetChainPath("Temp", 0)
        Dim Source As String() = GetMissingFiles(LoadedSettings.Paths.InputPath, LoadedSettings.Paths.OutputPath)
        If Source.Length = 0 Then Exit Sub

        Dim ThreadCount As Integer = GetThreads(LoadedSettings.BasicSettings.ThreadIndex, LoadedSettings.BasicSettings.ThreadCount, Source.Length)

        For i = 0 To Source.Length - 1 Step ThreadCount
            Dim ChainPaths As New List(Of String)
            Dim DeletedChainPaths As New List(Of String)
            ChainPaths.Add(TempPath)
            For j = 0 To ActiveChain.Count - 2
                Dim TempName As String = GetChainPath("Chain", j)
                ChainPaths.Add(TempName)
                If Directory.Exists(TempName) Then Directory.Delete(TempName, True)
                Directory.CreateDirectory(TempName)
            Next
            ChainPaths.Add(LoadedSettings.Paths.OutputPath)
            If Directory.Exists(TempPath) Then Directory.Delete(TempPath, True)
            Directory.CreateDirectory(TempPath)

            CopyFiles(Source, SkipList, TempPath, i, ThreadCount)

            For m = 0 To ActiveChain.Count - 1
                Dim Model As FormSettings.ChainObject = ActiveChain(m)
                Dim NewImages As New List(Of String)
                Dim DiffImages = GetMissingFiles(ChainPaths(0), LoadedSettings.Paths.OutputPath)
                For Each NewImage As String In DiffImages
                    Dim AcceptExt As Boolean = False
                    Try
                        If Model.Package IsNot Nothing Then
                            Dim FileTypesProp = Model.Package.GetType().GetProperty("FileTypes")
                            If FileTypesProp IsNot Nothing Then
                                Dim FileTypesVal = FileTypesProp.GetValue(Model.Package, Nothing)
                                If FileTypesVal IsNot Nothing Then
                                    AcceptExt = DirectCast(FileTypesVal, List(Of String)).Contains(Path.GetExtension(NewImage).ToLower)
                                Else
                                    AcceptExt = True
                                End If
                            Else
                                AcceptExt = True
                            End If
                        Else
                            AcceptExt = True
                        End If
                    Catch ex As Exception
                        AcceptExt = True
                    End Try

                    If File.Exists(NewImage) AndAlso AcceptExt = True Then
                        NewImages.Add(NewImage)
                        If LoadedSettings.BasicSettings.FixPS2 = True Then
                            If (m = 0 AndAlso Model.PackageType <> "TexConv") OrElse (ActiveChain(0).PackageType = "TexConv" AndAlso m = 1) Then
                                RemovePS2Alpha(NewImage)
                            End If
                        End If
                        If LoadedSettings.ExpertSettings.SeamlessMode > 0 Then
                            If (m = 0 AndAlso Model.PackageType <> "TexConv") OrElse (ActiveChain(0).PackageType = "TexConv" AndAlso m = 1) Then
                                Dim SeamlessImage As Bitmap = GetUnlockedImage(NewImage)
                                SeamlessImage = MakeSeamless(SeamlessImage, LoadedSettings.ExpertSettings.SeamlessMode, LoadedSettings.ExpertSettings.SeamlessMargin)
                                SeamlessImage.Save(NewImage)
                            End If
                        End If
                    End If
                Next

                StartBuilder(ChainPaths(0), ChainPaths(1), NewImages, Model)
                DeletedChainPaths.Add(ChainPaths(0))
                ChainPaths.RemoveAt(0)

                If (m = ActiveChain.Count - 1 AndAlso Model.PackageType <> "TexConv") OrElse (ActiveChain(ActiveChain.Count - 1).PackageType = "TexConv" AndAlso m = ActiveChain.Count - 2) Then
                    If LoadedSettings.BasicSettings.Defringe = True Then
                        For Each NewImage In NewImages
                            Dim ProcessedImgPath As String = ChainPaths(0) & "\" & Path.GetFileName(NewImage)
                            If File.Exists(ProcessedImgPath) Then Defringe(ProcessedImgPath, LoadedSettings.BasicSettings.DefringeThreshold)
                        Next
                    End If
                    If LoadedSettings.ExpertSettings.SeamlessMode > 0 Then
                        For Each NewImage In NewImages
                            Dim ProcessedImgPath As String = ChainPaths(0) & "\" & Path.GetFileName(NewImage)
                            If File.Exists(ProcessedImgPath) Then
                                Dim ScaleVal As Integer = LoadedSettings.ExpertSettings.SeamlessScale * LoadedSettings.ExpertSettings.SeamlessMargin
                                Dim CroppedImage As Bitmap = GetUnlockedImage(ProcessedImgPath)
                                CroppedImage = CropImage(CroppedImage, ScaleVal, ScaleVal, CroppedImage.Width - (ScaleVal * 2), CroppedImage.Height - (ScaleVal * 2), 0)
                                CroppedImage.Save(ProcessedImgPath)
                            End If
                        Next
                    End If
                    If LoadedSettings.BasicSettings.FixPS2 = True Then
                        For Each NewImage In NewImages
                            Dim ProcessedImgPath As String = ChainPaths(0) & "\" & Path.GetFileName(NewImage)
                            If File.Exists(ProcessedImgPath) Then
                                AddPS2Alpha(ProcessedImgPath)
                            End If
                        Next
                    End If
                End If

                If WorkHorse.CancellationPending = True Then
                    If Directory.Exists(TempPath) Then Directory.Delete(TempPath, True)
                    For j = 0 To ActiveChain.Count - 2
                        Dim TempName As String = GetChainPath("Chain", j)
                        If Directory.Exists(TempName) Then Directory.Delete(TempName, True)
                    Next
                    Exit Sub
                End If
            Next

            For Each ChainDir As String In DeletedChainPaths
                If Directory.Exists(ChainDir) Then Directory.Delete(ChainDir, True)
            Next

            WorkHorse.ReportProgress(CInt(Math.Min(100, Math.Floor(((i + 1) * 100) / Source.Length))))
        Next

        If CleanupCheckBox.Checked = True Then
            For Each SourceImage As String In Source
                If File.Exists(SourceImage) Then File.Delete(SourceImage)
            Next
        End If
    End Sub

#End Region

#Region "Upscale Subroutines"

    Private Sub CopyFiles(FileList As String(), ByRef SkipList As List(Of String), RootPath As String, CurrentIndex As Integer, BatchSize As Integer)
        Dim CopyCounter As Integer = 0
        Dim Idx As Integer = CurrentIndex
        Do While CopyCounter < BatchSize AndAlso Idx < FileList.Length
            Dim FilePath As String = FileList(Idx)
            If Not SkipList.Contains(FilePath) Then
                Select Case LoadedSettings.ExpertSettings.AlphaMode
                    Case 0
                        File.Copy(FilePath, RootPath & "\" & Path.GetFileName(FilePath), True)
                        CopyCounter += 1
                    Case 1
                        If Not GetHasTransparency(FilePath) Then
                            File.Copy(FilePath, RootPath & "\" & Path.GetFileName(FilePath), True)
                            CopyCounter += 1
                        Else
                            SkipList.Add(FilePath)
                        End If
                    Case 2
                        If GetHasTransparency(FilePath) Then
                            File.Copy(FilePath, RootPath & "\" & Path.GetFileName(FilePath), True)
                            CopyCounter += 1
                        Else
                            SkipList.Add(FilePath)
                        End If
                End Select
            End If
            Idx += 1
        Loop
    End Sub

    Private Sub StartBuilder(SourcePath As String, DestPath As String, ImageList As List(Of String), Model As FormSettings.ChainObject)
        If ImageList.Count > 0 Then
            Dim ExeFullPath As String = Root & Model.FileLocation
            Dim WorkingDir As String = Directory.GetParent(ExeFullPath).FullName

            If Model.PackageType = "ESRGAN" OrElse Model.PackageType.Contains("Vulkan") Then
                Dim Args As String = MakeCommand(SourcePath, DestPath, Model.PackageType, Model.Package)
                Dim BuildProcess As New ProcessStartInfo(ExeFullPath, Args) With {
                    .WorkingDirectory = WorkingDir,
                    .UseShellExecute = False,
                    .CreateNoWindow = True
                }
                RunSingleProcess(BuildProcess, LoadedSettings.ExpertSettings.Logging, LoadedSettings.Paths.OutputPath)
            Else
                Dim ProcessBag As New List(Of Process)
                For j = 0 To ImageList.Count - 1
                    Dim NewImage As String = DestPath & "\" & Path.GetFileName(ImageList(j))
                    Dim Args As String = MakeCommand(ImageList(j), NewImage, Model.PackageType, Model.Package)
                    Dim BuildProcess As New ProcessStartInfo(ExeFullPath, Args) With {
                        .WorkingDirectory = WorkingDir,
                        .UseShellExecute = False,
                        .CreateNoWindow = True
                    }
                    Dim BatchProcess As Process = Process.Start(BuildProcess)
                    ProcessBag.Add(BatchProcess)
                Next
                For Each Proc In ProcessBag
                    Proc.WaitForExit()
                    Proc.Dispose()
                Next
            End If

            For Each TempImage As String In Directory.GetFiles(SourcePath)
                Try
                    File.Delete(TempImage)
                Catch
                End Try
            Next
        End If
    End Sub

    Private Sub RunSingleProcess(StartInfo As ProcessStartInfo, LogOutput As Boolean, OutputDir As String)
        If LogOutput Then
            StartInfo.RedirectStandardOutput = True
            StartInfo.RedirectStandardError = True
            Dim StdOut As New System.Text.StringBuilder()
            Dim StdErr As New System.Text.StringBuilder()

            Using Proc As Process = Process.Start(StartInfo)
                AddHandler Proc.OutputDataReceived, Sub(sender As Object, e As DataReceivedEventArgs)
                                                        If e.Data IsNot Nothing Then
                                                            SyncLock StdOut
                                                                StdOut.AppendLine(e.Data)
                                                            End SyncLock
                                                        End If
                                                    End Sub
                AddHandler Proc.ErrorDataReceived, Sub(sender As Object, e As DataReceivedEventArgs)
                                                       If e.Data IsNot Nothing Then
                                                           SyncLock StdErr
                                                           StdErr.AppendLine(e.Data)
                                                       End SyncLock
                                                   End If
                                               End Sub
                Proc.BeginOutputReadLine()
                Proc.BeginErrorReadLine()
                Proc.WaitForExit()

                Dim Filename As String = OutputDir & "\Log_" & Now.ToString("yyyy-MM-dd_HH-mm-ss") & ".txt"
                Dim LogText As String = StartInfo.FileName & " " & StartInfo.Arguments & vbNewLine & vbNewLine & StdOut.ToString() & vbNewLine & vbNewLine & StdErr.ToString()
                Try
                    File.WriteAllText(Filename, LogText)
                Catch
                End Try
            End Using
        Else
            StartInfo.RedirectStandardOutput = False
            StartInfo.RedirectStandardError = False
            Using Proc As Process = Process.Start(StartInfo)
                Proc.WaitForExit()
            End Using
        End If
    End Sub

    Private Function GetChainPath(PathType As String, PathIndex As Integer) As String
        Return Path.GetTempPath & PathType & "_" & PathIndex & "_" & LoadedSettings.ExpertSettings.AlphaMode
    End Function

#End Region

#Region "Packageing"

    Private Function MakeCommand(Source As String, Dest As String, Mode As String, Package As Object) As String
        Select Case Mode
            Case "Waifu2x Caffe"
                Return MakeCaffeCommand(Source, Dest, DirectCast(Package, FormSettings.Waifu2xCaffePackage))
            Case "Waifu2x Vulkan"
                Return MakeVulkanCommand(Source, Dest, False, DirectCast(Package, FormSettings.VulkanNcnnPackage))
            Case "RealSR Vulkan"
                Return MakeVulkanCommand(Source, Dest, True, DirectCast(Package, FormSettings.VulkanNcnnPackage))
            Case "RealESRGAN Vulkan"
                Return MakeVulkanCommand(Source, Dest, True, DirectCast(Package, FormSettings.VulkanNcnnPackage))
            Case "SRMD Vulkan"
                Return MakeVulkanCommand(Source, Dest, False, DirectCast(Package, FormSettings.VulkanNcnnPackage))
            Case "Waifu2x CPP"
                Return MakeCPPCommand(Source, Dest, DirectCast(Package, FormSettings.Waifu2xCppPackage))
            Case "Anime4k CPP"
                Return MakeA4KCommand(Source, Dest, DirectCast(Package, FormSettings.Anime4kPackage))
            Case "TexConv"
                Return MakeTexConvCommand(Source, Dest, DirectCast(Package, FormSettings.DDxPackage))
            Case "xBRZ"
                Return MakeXBRZCommand(Source, Dest, DirectCast(Package, FormSettings.xBRZPackage))
            Case "ESRGAN"
                Return MakePyCommand(Source, Dest, DirectCast(Package, FormSettings.PythonPackage))
        End Select
        Return ""
    End Function

    Private Sub AddModelToChain(Mode As String, Optional AddPreview As Boolean = True)
        Select Case Mode
            Case "Waifu2x Caffe"
                Dim ItemName As String = "Caffe " & CaffeScale.Value & "x"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(0)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 0, CaffePath, "Waifu2x Caffe", Me))
            Case "Waifu2x Vulkan"
                Dim ItemName As String = "Waifu2x " & VulkanScale.Value & "x"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(1)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 1, WaifuNcnnPath, "Waifu2x Vulkan", Me))
            Case "RealSR Vulkan"
                Dim ItemName As String = "RealSR " & VulkanScale.Value & "x"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(2)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 2, RealSRNcnnPath, "RealSR Vulkan", Me))
            Case "RealESRGAN Vulkan"
                Dim ItemName As String = "RealESRGAN"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(8)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 8, RealESRGNcnnPath, "RealESRGAN Vulkan", Me))
            Case "SRMD Vulkan"
                Dim ItemName As String = "SRMD " & VulkanScale.Value & "x"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(3)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 3, SRMDNcnnPath, "SRMD Vulkan", Me))
            Case "Waifu2x CPP"
                Dim ItemName As String = "Waifu CPP " & WaifuCPPScale.Value & "x"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(4)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 4, WaifuCppPath, "Waifu2x CPP", Me))
            Case "Anime4k CPP"
                Dim ItemName As String = "Anime4k " & AnimeCPPScale.Value & "x"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(5)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 5, Anime4kPath, "Anime4k CPP", Me))
            Case "TexConv"
                Dim ItemName As String = "TexConv (" & IIf(DDxModeBox.SelectedIndex = 0, "In", "Out") & ")"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(7)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 7, TexConvPath, "TexConv", Me))
            Case "xBRZ"
                Dim ItemName As String = "xBRZ " & xBRZScale.Value & "x"
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ItemName, ChainThumbs.Item(0)))
                ChainList.Add(New FormSettings.ChainObject(ItemName, 0, xBRZPath, "xBRZ", Me))
            Case "ESRGAN"
                Dim ModelName As String = "ESRGAN"
                If PyModel.SelectedItem IsNot Nothing AndAlso PyModel.SelectedItem.ToString <> "" Then
                    ModelName = Path.GetFileNameWithoutExtension(PyModel.SelectedItem.ToString)
                ElseIf PyModels.Count > 0 AndAlso PyModel.SelectedIndex >= 0 AndAlso PyModel.SelectedIndex < PyModels.Count Then
                    ModelName = Path.GetFileNameWithoutExtension(PyModels(PyModel.SelectedIndex))
                End If
                If AddPreview Then ChainControl.ListItems.Add(New DragDropList.DragDropItem(ChainList.Count, ModelName, ChainThumbs.Item(6)))
                ChainList.Add(New FormSettings.ChainObject(ModelName, 6, PyPath, "ESRGAN", Me))
        End Select
        If AddPreview Then ChainControl.DrawList(ChainControl.ListItems)
    End Sub

    Private Function GetCurrentBackendChainObject() As FormSettings.ChainObject
        If ExeComboBox.SelectedItem Is Nothing Then Return Nothing
        Dim Mode As String = ExeComboBox.SelectedItem.ToString()
        Select Case Mode
            Case "Waifu2x Caffe"
                Return New FormSettings.ChainObject("Caffe " & CaffeScale.Value & "x", 0, CaffePath, "Waifu2x Caffe", Me)
            Case "Waifu2x Vulkan"
                Return New FormSettings.ChainObject("Waifu2x " & VulkanScale.Value & "x", 1, WaifuNcnnPath, "Waifu2x Vulkan", Me)
            Case "RealSR Vulkan"
                Return New FormSettings.ChainObject("RealSR " & VulkanScale.Value & "x", 2, RealSRNcnnPath, "RealSR Vulkan", Me)
            Case "RealESRGAN Vulkan"
                Return New FormSettings.ChainObject("RealESRGAN", 8, RealESRGNcnnPath, "RealESRGAN Vulkan", Me)
            Case "SRMD Vulkan"
                Return New FormSettings.ChainObject("SRMD " & VulkanScale.Value & "x", 3, SRMDNcnnPath, "SRMD Vulkan", Me)
            Case "Waifu2x CPP"
                Return New FormSettings.ChainObject("Waifu CPP " & WaifuCPPScale.Value & "x", 4, WaifuCppPath, "Waifu2x CPP", Me)
            Case "Anime4k CPP"
                Return New FormSettings.ChainObject("Anime4k " & AnimeCPPScale.Value & "x", 5, Anime4kPath, "Anime4k CPP", Me)
            Case "TexConv"
                Return New FormSettings.ChainObject("TexConv (" & IIf(DDxModeBox.SelectedIndex = 0, "In", "Out") & ")", 7, TexConvPath, "TexConv", Me)
            Case "xBRZ"
                Return New FormSettings.ChainObject("xBRZ " & xBRZScale.Value & "x", 0, xBRZPath, "xBRZ", Me)
            Case "ESRGAN"
                Dim ModelName As String = "ESRGAN"
                If PyModel.SelectedItem IsNot Nothing AndAlso PyModel.SelectedItem.ToString <> "" Then
                    ModelName = Path.GetFileNameWithoutExtension(PyModel.SelectedItem.ToString)
                ElseIf PyModels.Count > 0 AndAlso PyModel.SelectedIndex >= 0 AndAlso PyModel.SelectedIndex < PyModels.Count Then
                    ModelName = Path.GetFileNameWithoutExtension(PyModels(PyModel.SelectedIndex))
                End If
                Return New FormSettings.ChainObject(ModelName, 6, PyPath, "ESRGAN", Me)
        End Select
        Return Nothing
    End Function

#End Region

#Region "Commands"

    Private Function MakeCaffeCommand(SourceImage As String, NewImage As String, Package As FormSettings.Waifu2xCaffePackage) As String
        Dim Result As New ArguementString
        Result.AddArguement("-i", Quote(SourceImage))
        Result.AddArguement("-o", Quote(NewImage))
        Result.AddArguement(LoadedSettings.ExpertSettings.ExpertFlags)
        Result.AddArguement("-m", Package.Mode)
        Result.AddArguement("-s", Package.Scale.ToString)
        Result.AddArguement("-n", Package.Noise.ToString)
        Result.AddArguement("-p", Package.Process)
        Result.AddArguement("-t", IIf(Package.TAA = True, 1, 0))
        Return Result.GetArguements
    End Function

    Private Function MakeVulkanCommand(SourceImage As String, NewImage As String, NoNoise As Boolean, Package As FormSettings.VulkanNcnnPackage) As String
        Dim Result As New ArguementString
        Result.AddArguement("-i", Quote(SourceImage))
        Result.AddArguement("-o", Quote(NewImage))
        Result.AddArguement(LoadedSettings.ExpertSettings.ExpertFlags)
        Result.AddArguement("-s", Package.Scale.ToString)
        If NoNoise = False Then Result.AddArguement("-n", Package.Noise.ToString)
        Result.AddArguement("-f", Package.Format)
        Result.AddArguement(IIf(Package.TAA = True, "-x", ""))
        Return Result.GetArguements
    End Function

    Private Function MakeCPPCommand(SourceImage As String, NewImage As String, Package As FormSettings.Waifu2xCppPackage) As String
        Dim Result As New ArguementString
        Result.AddArguement("-i", Quote(SourceImage))
        Result.AddArguement("-o", Quote(Path.ChangeExtension(NewImage, Package.Format)))
        Result.AddArguement(LoadedSettings.ExpertSettings.ExpertFlags)
        Result.AddArguement("-m", Package.Mode)
        Result.AddArguement("--scale-ratio", Package.Scale.ToString)
        Result.AddArguement("--noise-level", Package.Noise.ToString)
        Result.AddArguement("-f", Package.Format)
        Result.AddArguement("--disable-gpu", Package.GPU)
        Result.AddArguement("--force-OpenCL", Package.ForceOpenCL)
        Return Result.GetArguements
    End Function

    Private Function MakeA4KCommand(SourceImage As String, NewImage As String, Package As FormSettings.Anime4kPackage) As String
        Dim Result As New ArguementString
        Result.AddArguement("-i", Quote(SourceImage))
        Result.AddArguement("-o", Quote(NewImage))
        Result.AddArguement(LoadedSettings.ExpertSettings.ExpertFlags)
        Result.AddArguement("-p", Package.Passes.ToString)
        Result.AddArguement("-n", Package.PushColors.ToString)
        Result.AddArguement("-c", Package.PushColorStrength.ToString)
        Result.AddArguement("-g", Package.PushGradStrength.ToString)
        Result.AddArguement("-z", Package.Scale.ToString)
        Result.AddArguement("-b", Package.PreProcess)
        Result.AddArguement("-r " & Package.PreFilterType, Package.PreFilter)
        Result.AddArguement("-a", Package.PostProcess)
        Result.AddArguement("-e " & Package.PostFilterType, Package.PostFilter)
        Result.AddArguement("-q", Package.GPU)
        Result.AddArguement("-w", Package.CNN)
        Result.AddArguement("-A")
        Return Result.GetArguements
    End Function

    Private Function MakeTexConvCommand(SourceImage As String, NewImage As String, Package As FormSettings.DDxPackage) As String
        Dim Result As New ArguementString
        Result.AddArguement("-f", Package.Format)
        Result.AddArguement("-nologo")
        Select Case Package.Mode
            Case "DDS Input"
                Result.AddArguement("-ft " & Package.ConversionFormat.ToLower)
            Case "DDS Output"
                Result.AddArguement("-fl " & Package.FeatureLevel, Package.FeatureLevel <> "11.0")
                Result.AddArguement("-dx9", Package.ForceDx9)
                Result.AddArguement("-dx10", Package.ForceDx10)
        End Select
        Result.AddArguement("-sepalpha", Package.SeperateAlpha)
        Result.AddArguement("-pmalpha", Package.PremultiplyAlpha)
        Result.AddArguement("-alpha", Package.StraightAlpha)
        Result.AddArguement("-o", Quote(Path.GetDirectoryName(NewImage).TrimEnd({"\"c, "/"c})))
        Result.AddArguement(Quote(SourceImage))
        Return Result.GetArguements
    End Function

    Private Function MakeXBRZCommand(SourceImage As String, NewImage As String, Package As FormSettings.xBRZPackage) As String
        Dim Result As New ArguementString
        Result.AddArguement("", "-" & CInt(Package.Scale) & "xBRZ")
        Result.AddArguement("", Quote(SourceImage))
        Result.AddArguement("", Quote(NewImage))
        Return Result.GetArguements
    End Function

    Private Function MakePyCommand(SourceFolder As String, DestFolder As String, Package As FormSettings.PythonPackage) As String
        Dim Result As New ArguementString
        Result.AddArguement(Quote(Package.Model))
        Result.AddArguement("--input", Quote(SourceFolder))
        Result.AddArguement("--output", Quote(DestFolder))
        Result.AddArguement("--tile_size", Package.TileSize.ToString)
        Result.AddArguement("--cpu", Package.CPUOnly.ToString)
        Return Result.GetArguements
    End Function

#End Region

#Region "Graphics"

    Private Function MakeSeamless(Source As Bitmap, Mirrored As Integer, Margin As Integer) As Bitmap
        Dim Result As New Bitmap(Source.Width * 3, Source.Height * 3, Source.PixelFormat)
        Using g As Graphics = Graphics.FromImage(Result)
            g.CompositingMode = Drawing2D.CompositingMode.SourceCopy
            g.PixelOffsetMode = Drawing2D.PixelOffsetMode.None
            g.SmoothingMode = Drawing2D.SmoothingMode.None
            g.InterpolationMode = Drawing2D.InterpolationMode.NearestNeighbor
            If Mirrored = 2 Then
                Dim X = Source.Width
                Dim Y = Source.Height
                Dim fX As New Bitmap(Source) : fX.RotateFlip(RotateFlipType.RotateNoneFlipX)
                Dim fY As New Bitmap(Source) : fY.RotateFlip(RotateFlipType.RotateNoneFlipY)
                Dim fXY As New Bitmap(Source) : fXY.RotateFlip(RotateFlipType.RotateNoneFlipXY)
                g.DrawImage(fXY, 0, 0, X, Y) : g.DrawImage(fY, X, 0, X, Y) : g.DrawImage(fXY, 2 * X, 0, X, Y)
                g.DrawImage(fX, 0, Y, X, Y) : g.DrawImage(Source, X, Y, X, Y) : g.DrawImage(fX, 2 * X, Y, X, Y)
                g.DrawImage(fXY, 0, 2 * Y, X, Y) : g.DrawImage(fY, X, 2 * Y, X, Y) : g.DrawImage(fXY, 2 * X, 2 * Y, X, Y)
            ElseIf Mirrored = 1 Then
                For i = 0 To Source.Width * 2 Step Source.Width
                    For j = 0 To Source.Height * 2 Step Source.Height
                        g.DrawImage(Source, i, j, Source.Width, Source.Height)
                    Next
                Next
            Else
                Return Source
            End If
        End Using
        Return CropImage(Result, Source.Width, Source.Height, Source.Width, Source.Height, Margin)
    End Function

    Private Function GetHasTransparency(Source As String) As Boolean
        Dim SourceImage As Bitmap = GetUnlockedImage(Source)
        Dim SourceRect As Rectangle = New Rectangle(0, 0, SourceImage.Width, SourceImage.Height)
        Dim SourceData As Imaging.BitmapData = SourceImage.LockBits(SourceRect, Imaging.ImageLockMode.ReadWrite, SourceImage.PixelFormat)
        Dim SourcePtr As IntPtr = SourceData.Scan0
        Dim SourceByteCount As Integer = Math.Abs(SourceData.Stride) * SourceImage.Height
        Dim SourceBytes As Byte() = New Byte(SourceByteCount - 1) {}
        Runtime.InteropServices.Marshal.Copy(SourcePtr, SourceBytes, 0, SourceByteCount)
        For i = 3 To SourceBytes.Length - 1 Step 4
            If SourceBytes(i) = 0 Then
                SourceImage.UnlockBits(SourceData)
                SourceImage.Dispose()
                Return True
            End If
        Next
        SourceImage.UnlockBits(SourceData)
        SourceImage.Dispose()
        Return False
    End Function

    Private Function CropImage(Source As Bitmap, OffsetX As Integer, OffsetY As Integer, Width As Integer, Height As Integer, Margins As Integer) As Bitmap
        Dim CropSize As New Rectangle(OffsetX - Margins, OffsetY - Margins, Width + (2 * Margins), Height + (2 * Margins))
        Dim Result = New Bitmap(CropSize.Width, CropSize.Height, Source.PixelFormat)
        Using g As Graphics = Graphics.FromImage(Result)
            g.CompositingMode = Drawing2D.CompositingMode.SourceCopy
            g.PixelOffsetMode = Drawing2D.PixelOffsetMode.None
            g.SmoothingMode = Drawing2D.SmoothingMode.None
            g.InterpolationMode = Drawing2D.InterpolationMode.NearestNeighbor
            g.DrawImage(Source, New Rectangle(0, 0, CropSize.Width, CropSize.Height), CropSize, GraphicsUnit.Pixel)
        End Using
        Return Result
    End Function

    Private Sub Defringe(Source As String, Threshold As Integer)
        Using NewImage As New DirectBitmap(GetUnlockedImage(Source))
            Dim TotalPixels As Integer = NewImage.Width * NewImage.Height
            Dim Bits As Integer() = NewImage.Bits
            For i = 0 To TotalPixels - 1
                Dim Argb As Integer = Bits(i)
                Dim A As Integer = (Argb >> 24) And &HFF
                If A < Threshold Then
                    Bits(i) = 0
                End If
            Next
            NewImage.Bitmap.Save(Source)
        End Using
    End Sub

    Private Sub RemovePS2Alpha(Source As String)
        Using NewImage As New DirectBitmap(GetUnlockedImage(Source))
            Dim TotalPixels As Integer = NewImage.Width * NewImage.Height
            Dim Bits As Integer() = NewImage.Bits
            Dim AlphaMax As Integer = 0
            For i = 0 To TotalPixels - 1
                Dim A As Integer = (Bits(i) >> 24) And &HFF
                If A > AlphaMax Then AlphaMax = A
                If AlphaMax > 128 Then Exit Sub
            Next
            For i = 0 To TotalPixels - 1
                Dim Argb As Integer = Bits(i)
                Dim A As Integer = (Argb >> 24) And &HFF
                If A <> 0 Then
                    Dim NewA As Integer = Math.Min(255, (A * 2) - 1)
                    Bits(i) = (NewA << 24) Or (Argb And &HFFFFFF)
                End If
            Next
            NewImage.Bitmap.Save(Source)
        End Using
    End Sub

    Private Sub AddPS2Alpha(Source As String)
        Using NewImage As New DirectBitmap(GetUnlockedImage(Source))
            Dim TotalPixels As Integer = NewImage.Width * NewImage.Height
            Dim Bits As Integer() = NewImage.Bits
            For i = 0 To TotalPixels - 1
                Dim Argb As Integer = Bits(i)
                Dim A As Integer = (Argb >> 24) And &HFF
                If A <> 0 Then
                    Dim NewA As Integer = (A + 1) \ 2
                    Bits(i) = (NewA << 24) Or (Argb And &HFFFFFF)
                End If
            Next
            NewImage.Bitmap.Save(Source)
        End Using
    End Sub

#End Region

#Region "XML"

    Private Shared Function GetExtraTypes() As Type()
        Return {
            GetType(FormSettings.Waifu2xCaffePackage),
            GetType(FormSettings.VulkanNcnnPackage),
            GetType(FormSettings.Waifu2xCppPackage),
            GetType(FormSettings.Anime4kPackage),
            GetType(FormSettings.DDxPackage),
            GetType(FormSettings.xBRZPackage),
            GetType(FormSettings.PythonPackage),
            GetType(FormSettings.ChainObject)
        }
    End Function

    Public Shared Function Serialize(Of T)(Source As T) As String
        Dim Result As String = ""
        Using XmlStream As New MemoryStream
            Dim XmlSerializer As New Xml.Serialization.XmlSerializer(GetType(T), GetExtraTypes())
            Dim XmlSettings As New Xml.XmlWriterSettings With {.Indent = True, .CloseOutput = True}
            Dim XmlWriter As Xml.XmlWriter = Xml.XmlWriter.Create(XmlStream, XmlSettings)
            XmlSerializer.Serialize(XmlWriter, Source)
            Dim XmlReader As New StreamReader(XmlStream)
            XmlStream.Position = 0
            Result = XmlReader.ReadToEnd()
            XmlWriter.Flush()
            XmlWriter.Close()
            XmlReader.Dispose()
        End Using
        Return Result
    End Function

    Public Shared Function Deserialize(Of T)(Xml As String) As T
        Dim Result As New Object
        Using XmlStream As New MemoryStream
            Dim XmlSerializer As New Xml.Serialization.XmlSerializer(GetType(T), GetExtraTypes())
            Dim XmlWriter As New StreamWriter(XmlStream)
            XmlWriter.Write(Xml)
            XmlWriter.Flush()
            XmlStream.Position = 0
            Dim XmlReader As New Xml.XmlTextReader(XmlStream)
            If XmlSerializer.CanDeserialize(XmlReader) Then
                Result = DirectCast(XmlSerializer.Deserialize(XmlReader), T)
            End If
            XmlWriter.Close()
            XmlReader.Dispose()
        End Using
        Return Result
    End Function

#End Region

#Region "Utils"

    Private Declare Function GetActiveWindow Lib "user32" Alias "GetActiveWindow" () As IntPtr

    Private Function GetMissingFiles(Path1 As String, Path2 As String) As String()
        Dim Result As New List(Of String)
        If Not Directory.Exists(Path1) Then Return Result.ToArray
        Dim Path1MasterList = Directory.GetFiles(Path1, "*.*", SearchOption.AllDirectories)
        Dim Path1List = Directory.GetFiles(Path1, "*.*", SearchOption.AllDirectories).ToList
        Dim Path2List As New List(Of String)
        If Directory.Exists(Path2) Then
            Path2List = Directory.GetFiles(Path2, "*.*", SearchOption.AllDirectories).ToList
        End If
        For i = 0 To Path1List.Count - 1
            Path1List(i) = Path.GetFileNameWithoutExtension(Path1List(i)).ToLower
        Next
        For i = 0 To Path2List.Count - 1
            Path2List(i) = Path.GetFileNameWithoutExtension(Path2List(i)).ToLower
        Next
        For i = 0 To Path1List.Count - 1
            If Not Path2List.Contains(Path1List(i)) Then Result.Add(Path1MasterList(i))
        Next
        Return Result.ToArray
    End Function

    Private Function GetThreads(Index As Integer, Count As Integer, Optional TotalFiles As Integer = 512) As Integer
        Select Case Index
            Case 0 ' Single
                Return 1
            Case 1 ' Custom
                Return Math.Max(1, Count)
            Case 2 ' All
                Return Math.Max(1, TotalFiles)
            Case 3 ' Max (512)
                Return 512
        End Select
        Return Math.Max(1, TotalFiles)
    End Function

    Private Function GetUnlockedImage(Source As String) As Bitmap
        Dim SourceImage As Bitmap = Image.FromFile(Source)
        Dim UnlockedImage As New Bitmap(SourceImage)
        SourceImage.Dispose()
        Return UnlockedImage
    End Function

    Private Function GetFolder() As String
        Using FBD As New FolderBrowserDialog
            If FBD.ShowDialog = DialogResult.OK Then
                Return FBD.SelectedPath
            End If
        End Using
        Return ""
    End Function

    Private Function Quote(Source As String) As String
        Return ControlChars.Quote & Source & ControlChars.Quote
    End Function

    Private Sub WriteLog(Source As Process, SaveLoc As String)
        Dim Filename As String = SaveLoc & "\Log_" & Now.ToString("yyyy-MM-dd_HH-mm-ss") & ".txt"
        Dim Output As String = ""
        Output += Source.StartInfo.FileName & " "
        Output += Source.StartInfo.Arguments
        Output += vbNewLine & vbNewLine
        Output += Source.StandardOutput.ReadToEnd
        Output += vbNewLine & vbNewLine
        Output += Source.StandardError.ReadToEnd
        File.WriteAllText(Filename, Output)
    End Sub

#End Region

End Class
