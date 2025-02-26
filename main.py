import sys
import os
import shutil
import subprocess
import tempfile
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox, 
                            QTextEdit, QProgressBar, QMessageBox, QTabWidget, QFormLayout,
                            QListWidget, QListWidgetItem, QCheckBox, QScrollArea, QFrame,
                            QSplitter)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize

class IconExtractorThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        
    def run(self):
        try:
            # Create temp directory
            temp_dir = tempfile.mkdtemp()
            self.progress.emit(20)
            
            # Check if file is an AppImage
            if self.file_path.lower().endswith('.appimage'):
                # Extract AppImage
                cmd = [self.file_path, '--appimage-extract']
                subprocess.run(cmd, cwd=temp_dir, check=True)
                self.progress.emit(50)
                
                # Look for icon in extracted content
                squashfs_root = os.path.join(temp_dir, 'squashfs-root')
                icon_path = None
                
                # Check common locations for icons
                possible_locations = [
                    os.path.join(squashfs_root, '.DirIcon'),
                    os.path.join(squashfs_root, 'usr', 'share', 'icons'),
                    os.path.join(squashfs_root, 'usr', 'share', 'pixmaps')
                ]
                
                for loc in possible_locations:
                    if os.path.isfile(loc):
                        icon_path = loc
                        break
                    elif os.path.isdir(loc):
                        # Find the first png or svg file
                        for root, dirs, files in os.walk(loc):
                            for file in files:
                                if file.lower().endswith(('.png', '.svg', '.xpm')):
                                    icon_path = os.path.join(root, file)
                                    break
                            if icon_path:
                                break
                    if icon_path:
                        break
                
                self.progress.emit(80)
                
                if icon_path:
                    # Save the icon to a known location
                    saved_icon_path = os.path.join(temp_dir, 'extracted_icon.png')
                    shutil.copy(icon_path, saved_icon_path)
                    self.progress.emit(100)
                    self.finished.emit(saved_icon_path)
                else:
                    self.error.emit("No icon found in the AppImage")
            else:
                # For non-AppImage executables, try to extract icon
                # This is a simplified approach as actual extraction would be complex
                self.error.emit("Icon extraction is currently only supported for AppImage files")
        except Exception as e:
            self.error.emit(f"Error extracting icon: {str(e)}")
            
        # Cleanup will happen when app closes

class AppInstallThread(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, app_data, system_wide=False):
        super().__init__()
        self.app_data = app_data
        self.system_wide = system_wide
        
    def run(self):
        try:
            # Determine installation directories based on install type
            if self.system_wide:
                # System-wide installation requires sudo/root
                app_dir = "/usr/share/applications"
                bin_dir = "/usr/local/bin"
                icon_dir = "/usr/share/icons/hicolor/256x256/apps"
                use_sudo = True
            else:
                # User local installation
                app_dir = os.path.expanduser("~/.local/share/applications")
                bin_dir = os.path.expanduser("~/.local/bin")
                icon_dir = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps")
                use_sudo = False
            
            # Create necessary directories
            if not self.system_wide:
                os.makedirs(app_dir, exist_ok=True)
                os.makedirs(bin_dir, exist_ok=True)
                os.makedirs(icon_dir, exist_ok=True)
            
            self.progress.emit(20)
            
            # Copy executable to bin directory
            exe_name = os.path.basename(self.app_data['executable_path'])
            if self.app_data['app_name']:
                new_exe_name = self.app_data['app_name'].lower().replace(' ', '-')
                if not new_exe_name.endswith('.appimage') and exe_name.endswith('.appimage'):
                    new_exe_name += '.appimage'
            else:
                new_exe_name = exe_name
                
            dest_exe_path = os.path.join(bin_dir, new_exe_name)
            
            if self.system_wide:
                # Use pkexec or sudo for system-wide installation
                subprocess.run(['pkexec', 'cp', self.app_data['executable_path'], dest_exe_path], check=True)
                subprocess.run(['pkexec', 'chmod', '755', dest_exe_path], check=True)
            else:
                shutil.copy2(self.app_data['executable_path'], dest_exe_path)
                os.chmod(dest_exe_path, 0o755)  # Make executable
            
            self.progress.emit(50)
            
            # Copy icon if available
            if self.app_data['icon_path']:
                icon_name = f"{new_exe_name.split('.')[0]}.png"
                dest_icon_path = os.path.join(icon_dir, icon_name)
                
                if self.system_wide:
                    subprocess.run(['pkexec', 'cp', self.app_data['icon_path'], dest_icon_path], check=True)
                else:
                    shutil.copy2(self.app_data['icon_path'], dest_icon_path)
            else:
                icon_name = ""
            
            # Create desktop entry
            desktop_file_content = [
                "[Desktop Entry]",
                f"Name={self.app_data['app_name'] or os.path.splitext(exe_name)[0]}",
                f"Exec={dest_exe_path}",
                f"Type=Application",
                f"Categories={self.app_data['category'] or 'Utility'}"
            ]
            
            if icon_name:
                desktop_file_content.append(f"Icon={os.path.splitext(icon_name)[0]}")
                
            if self.app_data['keywords']:
                desktop_file_content.append(f"Keywords={self.app_data['keywords']}")
                
            if self.app_data['description']:
                desktop_file_content.append(f"Comment={self.app_data['description']}")
                
            desktop_file_path = os.path.join(app_dir, f"{new_exe_name.split('.')[0]}.desktop")
            
            # Write the desktop file
            if self.system_wide:
                # Create temporary file and move it with sudo
                temp_desktop_file = tempfile.mktemp()
                with open(temp_desktop_file, 'w') as f:
                    f.write('\n'.join(desktop_file_content))
                subprocess.run(['pkexec', 'cp', temp_desktop_file, desktop_file_path], check=True)
                os.remove(temp_desktop_file)
                
                # Update desktop database
                subprocess.run(['pkexec', 'update-desktop-database'], check=True)
            else:
                with open(desktop_file_path, 'w') as f:
                    f.write('\n'.join(desktop_file_content))
                
            self.progress.emit(100)
            self.finished.emit()
            
        except Exception as e:
            self.error.emit(f"Error installing application: {str(e)}")

class AppManagerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("Linux App Manager")
        self.setMinimumSize(900, 650)
        
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # Create tabs
        tabs = QTabWidget()
        
        # Install tab
        install_tab = QWidget()
        install_layout = QVBoxLayout()
        
        # File selection
        file_layout = QHBoxLayout()
        file_label = QLabel("Executable:")
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(browse_button)
        
        # App details form
        form_widget = QWidget()
        form_layout = QFormLayout()
        
        self.app_name = QLineEdit()
        form_layout.addRow("Application Name:", self.app_name)
        
        # Icon selection
        icon_layout = QHBoxLayout()
        self.icon_path = QLineEdit()
        self.icon_path.setReadOnly(True)
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(48, 48)
        self.icon_preview.setAlignment(Qt.AlignCenter)
        browse_icon_button = QPushButton("Browse")
        browse_icon_button.clicked.connect(self.browse_icon)
        extract_icon_button = QPushButton("Extract from App")
        extract_icon_button.clicked.connect(self.extract_icon)
        icon_layout.addWidget(self.icon_path)
        icon_layout.addWidget(browse_icon_button)
        icon_layout.addWidget(extract_icon_button)
        icon_layout.addWidget(self.icon_preview)
        form_layout.addRow("Icon:", icon_layout)
        
        # Category selection
        self.category = QComboBox()
        categories = [
            "AudioVideo", "Development", "Education", "Game", "Graphics",
            "Network", "Office", "Science", "Settings", "System", "Utility"
        ]
        self.category.addItems(categories)
        form_layout.addRow("Category:", self.category)
        
        # Keywords
        self.keywords = QLineEdit()
        form_layout.addRow("Keywords (comma separated):", self.keywords)
        
        # Description
        self.description = QTextEdit()
        self.description.setMaximumHeight(80)
        form_layout.addRow("Description:", self.description)
        
        # Dependencies
        dependencies_label = QLabel("Dependencies:")
        self.dependencies = QListWidget()
        self.dependencies.setMaximumHeight(100)
        add_dependency_layout = QHBoxLayout()
        self.new_dependency = QLineEdit()
        add_dependency_button = QPushButton("Add")
        add_dependency_button.clicked.connect(self.add_dependency)
        add_dependency_layout.addWidget(self.new_dependency)
        add_dependency_layout.addWidget(add_dependency_button)
        
        remove_dependency_button = QPushButton("Remove Selected")
        remove_dependency_button.clicked.connect(self.remove_dependency)
        
        form_layout.addRow(dependencies_label)
        form_layout.addRow(self.dependencies)
        form_layout.addRow(add_dependency_layout)
        form_layout.addRow(remove_dependency_button)
        
        # System-wide installation option
        self.system_wide_install = QCheckBox("Install system-wide (requires admin privileges)")
        form_layout.addRow(self.system_wide_install)
        
        form_widget.setLayout(form_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        install_button = QPushButton("Install Application")
        install_button.clicked.connect(self.install_app)
        clear_button = QPushButton("Clear All")
        clear_button.clicked.connect(self.clear_form)
        buttons_layout.addWidget(clear_button)
        buttons_layout.addWidget(install_button)
        
        # Add all to install layout
        install_layout.addLayout(file_layout)
        install_layout.addWidget(form_widget)
        install_layout.addWidget(self.progress_bar)
        install_layout.addLayout(buttons_layout)
        
        install_tab.setLayout(install_layout)
        
        # Manage tab
        manage_tab = QWidget()
        manage_layout = QVBoxLayout()
        
        refresh_button = QPushButton("Refresh Installed Apps")
        refresh_button.clicked.connect(self.refresh_installed_apps)
        
        # Create a splitter for the list and details
        splitter = QSplitter(Qt.Horizontal)
        
        # Left side: list of apps
        list_container = QWidget()
        list_layout = QVBoxLayout()
        list_layout.addWidget(QLabel("Installed Applications:"))
        
        self.installed_apps_list = QListWidget()
        self.installed_apps_list.itemClicked.connect(self.show_app_details)
        list_layout.addWidget(self.installed_apps_list)
        
        list_container.setLayout(list_layout)
        splitter.addWidget(list_container)
        
        # Right side: app details
        details_container = QWidget()
        details_layout = QVBoxLayout()
        details_layout.addWidget(QLabel("Application Details:"))
        
        # Use a scroll area for details to handle overflow
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.app_details_widget = QWidget()
        self.app_details_layout = QVBoxLayout(self.app_details_widget)
        
        details_scroll.setWidget(self.app_details_widget)
        details_layout.addWidget(details_scroll)
        
        # Buttons for app actions
        actions_layout = QHBoxLayout()
        launch_button = QPushButton("Launch Selected")
        launch_button.clicked.connect(self.launch_selected_app)
        uninstall_button = QPushButton("Uninstall Selected")
        uninstall_button.clicked.connect(self.uninstall_app)
        actions_layout.addWidget(launch_button)
        actions_layout.addWidget(uninstall_button)
        details_layout.addLayout(actions_layout)
        
        details_container.setLayout(details_layout)
        splitter.addWidget(details_container)
        
        # Set the initial sizes of the splitter
        splitter.setSizes([300, 600])
        
        manage_layout.addWidget(refresh_button)
        manage_layout.addWidget(splitter)
        
        manage_tab.setLayout(manage_layout)
        
        # Add tabs
        tabs.addTab(install_tab, "Install")
        tabs.addTab(manage_tab, "Manage")
        
        main_layout.addWidget(tabs)
        
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # Set stylesheet for a colorful, modern look
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #f0f0f0;
                color: #333;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton {
                background-color: #4a86e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a76d8;
            }
            QPushButton:pressed {
                background-color: #2a66c8;
            }
            QLineEdit, QTextEdit, QComboBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
                background-color: white;
            }
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-radius: 4px;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                border: 1px solid #ccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4a86e8;
                color: white;
            }
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4a86e8;
                width: 10px;
            }
            QLabel {
                color: #333;
            }
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
            }
            QFrame {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                padding: 8px;
            }
            QScrollArea {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
            }
            QCheckBox {
                color: #333;
            }
            QCheckBox::indicator {
                border: 1px solid #ccc;
                border-radius: 2px;
                width: 15px;
                height: 15px;
            }
            QCheckBox::indicator:checked {
                background-color: #4a86e8;
            }
            QSplitter::handle {
                background-color: #ccc;
            }
            QSplitter::handle:horizontal {
                width: 4px;
            }
            QSplitter::handle:vertical {
                height: 4px;
            }
        """)
        
        # Initialize the manage tab with installed apps
        self.refresh_installed_apps()
        
    def browse_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Executable", "", "All Files (*);;AppImage Files (*.appimage)"
        )
        if file_name:
            self.file_path.setText(file_name)
            # Try to guess the app name from the file name
            base_name = os.path.basename(file_name)
            name_without_ext = os.path.splitext(base_name)[0]
            # Format the name nicely (capitalize words, replace dashes with spaces)
            nice_name = ' '.join(word.capitalize() for word in name_without_ext.replace('-', ' ').split())
            self.app_name.setText(nice_name)
            
    def browse_icon(self):
        icon_path, _ = QFileDialog.getOpenFileName(
            self, "Select Icon", "", "Image Files (*.png *.jpg *.svg)"
        )
        if icon_path:
            self.icon_path.setText(icon_path)
            self.update_icon_preview(icon_path)
            
    def extract_icon(self):
        if not self.file_path.text():
            QMessageBox.warning(self, "Warning", "Please select an executable first.")
            return
            
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.icon_extractor = IconExtractorThread(self.file_path.text())
        self.icon_extractor.progress.connect(self.update_progress)
        self.icon_extractor.finished.connect(self.icon_extracted)
        self.icon_extractor.error.connect(self.show_error)
        self.icon_extractor.start()
        
    def update_progress(self, value):
        self.progress_bar.setValue(value)
        
    def icon_extracted(self, icon_path):
        self.icon_path.setText(icon_path)
        self.update_icon_preview(icon_path)
        self.progress_bar.setVisible(False)
        
    def update_icon_preview(self, icon_path):
        if icon_path and os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_preview.setPixmap(pixmap)
            else:
                self.icon_preview.setText("Invalid")
        else:
            self.icon_preview.clear()
            
    def add_dependency(self):
        dependency = self.new_dependency.text().strip()
        if dependency:
            self.dependencies.addItem(dependency)
            self.new_dependency.clear()
            
    def remove_dependency(self):
        selected_items = self.dependencies.selectedItems()
        for item in selected_items:
            self.dependencies.takeItem(self.dependencies.row(item))
            
    def install_app(self):
        if not self.file_path.text():
            QMessageBox.warning(self, "Warning", "Please select an executable file.")
            return
            
        # Check if system-wide install is selected
        system_wide = self.system_wide_install.isChecked()
        
        if system_wide:
            reply = QMessageBox.warning(
                self, "System-wide Installation",
                "You are about to install this application system-wide.\n"
                "This requires administrative privileges and will affect all users on this system.\n\n"
                "Are you sure you want to continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
                
        # Collect all app data
        dependencies = []
        for i in range(self.dependencies.count()):
            dependencies.append(self.dependencies.item(i).text())
            
        app_data = {
            'executable_path': self.file_path.text(),
            'app_name': self.app_name.text(),
            'icon_path': self.icon_path.text(),
            'category': self.category.currentText(),
            'keywords': self.keywords.text(),
            'description': self.description.toPlainText(),
            'dependencies': dependencies
        }
        
        # Install dependencies if any
        if dependencies:
            reply = QMessageBox.question(
                self, "Install Dependencies",
                f"Do you want to install the following dependencies?\n{', '.join(dependencies)}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # This would need proper implementation to install dependencies
                # For now just showing a message
                QMessageBox.information(
                    self, "Dependencies", 
                    "Dependencies installation would happen here.\nContinuing with app installation."
                )
                
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Start installation thread
        self.install_thread = AppInstallThread(app_data, system_wide)
        self.install_thread.progress.connect(self.update_progress)
        self.install_thread.finished.connect(self.installation_complete)
        self.install_thread.error.connect(self.show_error)
        self.install_thread.start()
        
    def installation_complete(self):
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "Success", "Application installed successfully!")
        self.clear_form()
        # Refresh the apps list
        self.refresh_installed_apps()
        
    def clear_form(self):
        self.file_path.clear()
        self.app_name.clear()
        self.icon_path.clear()
        self.icon_preview.clear()
        self.category.setCurrentIndex(0)
        self.keywords.clear()
        self.description.clear()
        self.dependencies.clear()
        self.new_dependency.clear()
        self.system_wide_install.setChecked(False)
        
    def show_error(self, message):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Error", message)
        
    def refresh_installed_apps(self):
        self.installed_apps_list.clear()
        
        # Clear app details
        self.clear_app_details()
        
        # Look for .desktop files in user and system locations
        app_locations = [
            os.path.expanduser("~/.local/share/applications"),  # User applications
            "/usr/share/applications"  # System applications
        ]
        
        for app_dir in app_locations:
            if os.path.exists(app_dir):
                for file_name in os.listdir(app_dir):
                    if file_name.endswith('.desktop'):
                        # Create an item with the full path as user data
                        item = QListWidgetItem(file_name)
                        item.setData(Qt.UserRole, os.path.join(app_dir, file_name))
                        self.installed_apps_list.addItem(item)
        
    def clear_app_details(self):
        # Clear all widgets from the details layout
        while self.app_details_layout.count():
            item = self.app_details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
    def show_app_details(self, item):
        # Clear previous details
        self.clear_app_details()
        
        # Get full path from item data
        desktop_file = item.data(Qt.UserRole)
        
        if os.path.exists(desktop_file):
            # Determine if system or user app
            is_system_app = desktop_file.startswith("/usr")
            
            # Create a container for all details with its own layout
            details_container = QWidget()
            details_form = QFormLayout(details_container)
            
            # Add indicator for system vs user app
            install_type = QLabel("System Application" if is_system_app else "User Application")
            install_type.setStyleSheet(
                "background-color: #ff9800; color: white; padding: 5px; border-radius: 3px;" 
                if is_system_app else 
                "background-color: #4caf50; color: white; padding: 5px; border-radius: 3px;"
            )
            details_form.addRow("Installation Type:", install_type)
            
            # Parse desktop file
            details = {}
            with open(desktop_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        details[key] = value
            
            # Display details
            for key, value in details.items():
                if key == "Icon":
                    # Try to find and show the icon
                    icon_label = QLabel()
                    icon_label.setFixedSize(48, 48)
                    
                    # Check common icon locations
                    icon_paths = [
                        os.path.expanduser(f"~/.local/share/icons/hicolor/256x256/apps/{value}.png"),
                        os.path.expanduser(f"~/.local/share/icons/hicolor/128x128/apps/{value}.png"),
                        os.path.expanduser(f"~/.local/share/icons/hicolor/64x64/apps/{value}.png"),
                        os.path.expanduser(f"~/.local/share/icons/hicolor/48x48/apps/{value}.png"),
                        os.path.expanduser(f"/usr/share/icons/hicolor/256x256/apps/{value}.png"),
                        os.path.expanduser(f"/usr/share/icons/hicolor/128x128/apps/{value}.png"),
                        os.path.expanduser(f"/usr/share/icons/hicolor/64x64/apps/{value}.png"),
                        os.path.expanduser(f"/usr/share/icons/hicolor/48x48/apps/{value}.png")
                    ]
                    
                    icon_found = False
                    for icon_path in icon_paths:
                        if os.path.exists(icon_path):
                            pixmap = QPixmap(icon_path)
                            pixmap = pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            icon_label.setPixmap(pixmap)
                            icon_found = True
                            break
                            
                    if not icon_found:
                        icon_label.setText("No icon")
                        
                    details_form.addRow(f"{key}:", icon_label)
                else:
                    value_label = QLabel(value)
                    value_label.setWordWrap(True)
                    details_form.addRow(f"{key}:", value_label)
            
            # Add the details container to the main layout
            self.app_details_layout.addWidget(details_container)
            
    def launch_selected_app(self):
        selected_items = self.installed_apps_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select an application to launch.")
            return
            
        desktop_file = selected_items[0].data(Qt.UserRole)
        
        if os.path.exists(desktop_file):
            try:
                # Parse desktop file to find executable
                exec_path = None
                with open(desktop_file, 'r') as f:
                    for line in f:
                        if line.startswith("Exec="):
                            exec_command = line.strip().split("=", 1)[1]
                            # Extract command before any % parameters
                            exec_path = exec_command.split()[0]
                            break
                
                if exec_path:
                    # Launch in background
                    subprocess.Popen([exec_path], start_new_session=True)
                else:
                    QMessageBox.warning(self, "Error", "Could not find executable in desktop file.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to launch application: {str(e)}")
                
    def uninstall_app(self):
        selected_items = self.installed_apps_list.selectedItems()
        if not selected_items:
            return
            
        desktop_file = selected_items[0].text()
        
        reply = QMessageBox.question(
            self, "Confirm Uninstallation",
            f"Are you sure you want to uninstall {desktop_file.split('.')[0]}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Get the executable path from the desktop file
                desktop_file_path = os.path.join(
                    os.path.expanduser("~/.local/share/applications"), 
                    desktop_file
                )
                
                exec_path = None
                with open(desktop_file_path, 'r') as f:
                    for line in f:
                        if line.startswith("Exec="):
                            exec_path = line.strip().split("=", 1)[1].split()[0]
                            break
                
                # Remove the desktop file
                os.remove(desktop_file_path)
                
                # Remove the executable if it's in user's bin
                if exec_path and exec_path.startswith(os.path.expanduser("~/.local/bin")):
                    os.remove(exec_path)
                    
                QMessageBox.information(self, "Success", "Application uninstalled successfully.")
                self.refresh_installed_apps()
                
                # Clear the details pane
                while self.app_details_layout.count():
                    child = self.app_details_layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                        
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to uninstall application: {str(e)}")

def main():
    app = QApplication(sys.argv)
    window = AppManagerGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()