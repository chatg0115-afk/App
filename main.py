"""
APK URL Extractor - Fixed 2025
Compatible with latest Kivy & Android
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
import re
import threading
import os

# Try to import androguard
try:
    from androguard.core.bytecodes.apk import APK
    ANDROGUARD_AVAILABLE = True
except ImportError:
    ANDROGUARD_AVAILABLE = False
    print("Warning: androguard not available")

# Set window background
Window.clearcolor = (0.15, 0.15, 0.2, 1)


class GradientButton(Button):
    """Modern styled button"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = (0, 0, 0, 0)
        self.background_normal = ''
        with self.canvas.before:
            Color(0.2, 0.6, 0.86, 1)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[15])
        self.bind(pos=self.update_rect, size=self.update_rect)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class URLExtractorApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_apk = None
        self.extracted_urls = []
        
        # Ad domains to filter
        self.ad_domains = [
            'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
            'facebook.com/tr', 'google-analytics.com', 'googletagmanager.com',
            'ads.', 'adservice', 'analytics', 'tracking', 'metric', 'telemetry',
            'crashlytics', 'firebase.com', 'amazonaws.com', 'cloudfront.net',
            'appspot.com', 'unity3d.com', 'appsflyer', 'adjust.com',
            'googleapis.com', 'gstatic.com'
        ]

    def build(self):
        # Check androguard
        if not ANDROGUARD_AVAILABLE:
            return self.build_error_screen()
        
        # Main layout
        layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        
        # Header
        header = Label(
            text='APK URL Extractor',
            size_hint_y=0.08,
            font_size='22sp',
            bold=True,
            color=(1, 1, 1, 1)
        )
        layout.add_widget(header)
        
        # Subtitle
        subtitle = Label(
            text='Extract • Filter • Save',
            size_hint_y=0.04,
            font_size='13sp',
            color=(0.7, 0.9, 1, 1)
        )
        layout.add_widget(subtitle)
        
        # Select APK button
        self.select_btn = GradientButton(
            text='Select APK File',
            size_hint_y=0.08,
            font_size='16sp'
        )
        self.select_btn.bind(on_press=self.select_apk)
        layout.add_widget(self.select_btn)
        
        # Extract button
        self.extract_btn = GradientButton(
            text='Extract URLs',
            size_hint_y=0.08,
            font_size='16sp',
            disabled=True
        )
        self.extract_btn.bind(on_press=self.extract_urls)
        layout.add_widget(self.extract_btn)
        
        # Progress bar
        self.progress = ProgressBar(max=100, size_hint_y=0.03)
        self.progress.value = 0
        layout.add_widget(self.progress)
        
        # Status label
        self.status_label = Label(
            text='Ready to extract URLs',
            size_hint_y=0.05,
            font_size='13sp',
            color=(0.5, 1, 0.5, 1)
        )
        layout.add_widget(self.status_label)
        
        # Results area
        scroll = ScrollView(size_hint_y=0.5)
        self.results_label = Label(
            text='URLs will appear here...',
            size_hint_y=None,
            font_size='12sp',
            color=(0.9, 0.9, 0.9, 1),
            halign='left',
            valign='top',
            text_size=(Window.width - 40, None)
        )
        self.results_label.bind(
            texture_size=self.results_label.setter('size')
        )
        scroll.add_widget(self.results_label)
        layout.add_widget(scroll)
        
        # Save button
        self.save_btn = GradientButton(
            text='Save Results',
            size_hint_y=0.08,
            font_size='16sp',
            disabled=True
        )
        self.save_btn.bind(on_press=self.save_results)
        layout.add_widget(self.save_btn)
        
        return layout

    def build_error_screen(self):
        """Show error if androguard not available"""
        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        error_label = Label(
            text='ERROR: Androguard not installed!\n\n'
                 'Install with:\npip install androguard',
            font_size='16sp',
            color=(1, 0.3, 0.3, 1),
            halign='center'
        )
        layout.add_widget(error_label)
        return layout

    def select_apk(self, instance):
        """Open file chooser"""
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # File chooser - check multiple paths
        paths = ['/sdcard', '/storage/emulated/0', os.path.expanduser('~')]
        start_path = paths[0]
        for path in paths:
            if os.path.exists(path):
                start_path = path
                break
        
        filechooser = FileChooserListView(
            filters=['*.apk'],
            path=start_path
        )
        content.add_widget(filechooser)
        
        # Buttons
        btn_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        select_button = Button(text='Select', size_hint_x=0.5)
        cancel_button = Button(text='Cancel', size_hint_x=0.5)
        
        btn_layout.add_widget(select_button)
        btn_layout.add_widget(cancel_button)
        content.add_widget(btn_layout)
        
        # Popup
        popup = Popup(
            title='Choose APK File',
            content=content,
            size_hint=(0.95, 0.9)
        )
        
        def on_select(btn):
            if filechooser.selection:
                self.selected_apk = filechooser.selection[0]
                filename = os.path.basename(self.selected_apk)
                short_name = filename[:30] + '...' if len(filename) > 30 else filename
                self.select_btn.text = f'{short_name}'
                self.extract_btn.disabled = False
                self.status_label.text = 'APK selected! Ready to extract.'
                self.status_label.color = (0.5, 1, 0.5, 1)
            popup.dismiss()
        
        select_button.bind(on_press=on_select)
        cancel_button.bind(on_press=popup.dismiss)
        
        popup.open()

    def extract_urls(self, instance):
        """Extract URLs from APK"""
        if not self.selected_apk or not ANDROGUARD_AVAILABLE:
            return
        
        self.extract_btn.disabled = True
        self.status_label.text = 'Extracting URLs...'
        self.status_label.color = (1, 1, 0, 1)
        self.progress.value = 0
        self.results_label.text = 'Processing...'
        
        # Run in thread
        thread = threading.Thread(target=self._extract_worker)
        thread.daemon = True
        thread.start()

    def _extract_worker(self):
        """Worker thread for extraction"""
        try:
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 10), 0)
            
            # Load APK
            apk = APK(self.selected_apk)
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 30), 0)
            
            # Extract URLs
            urls_set = set()
            
            # From manifest
            try:
                manifest = apk.get_android_manifest_xml()
                urls_set.update(self._extract_urls_from_text(str(manifest)))
            except Exception as e:
                print(f"Manifest error: {e}")
            
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 50), 0)
            
            # From resources
            try:
                files = apk.get_files()
                for idx, file in enumerate(files):
                    if file.endswith(('.xml', '.json', '.txt', '.html')):
                        try:
                            content = apk.get_file(file)
                            if content:
                                text = content.decode('utf-8', errors='ignore')
                                urls_set.update(self._extract_urls_from_text(text))
                        except:
                            pass
                    
                    # Update progress
                    if idx % 100 == 0:
                        progress = 50 + int((idx / len(files)) * 30)
                        Clock.schedule_once(
                            lambda dt, p=progress: setattr(self.progress, 'value', p), 0
                        )
            except Exception as e:
                print(f"Files error: {e}")
            
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 90), 0)
            
            # Filter ads
            filtered_urls = [
                url for url in urls_set 
                if not self._is_ad_domain(url) and self._is_valid_url(url)
            ]
            self.extracted_urls = sorted(filtered_urls)
            
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 100), 0)
            Clock.schedule_once(self._update_results, 0)
            
        except Exception as e:
            error_msg = f'Error: {str(e)}'
            Clock.schedule_once(lambda dt: self._show_error(error_msg), 0)

    def _extract_urls_from_text(self, text):
        """Extract URLs using regex"""
        if not text:
            return set()
        
        # URL patterns
        patterns = [
            r'https?://[^\s"\'<>)}\]]+',
            r'(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(?:\.[a-zA-Z]{2,})+(?:[/?#][^\s"\'<>)}\]]*)?'
        ]
        
        urls = set()
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Clean URL
                    cleaned = re.sub(r'^https?://', '', match)
                    cleaned = re.sub(r'^www\.', '', cleaned)
                    domain = cleaned.split('/')[0].split('?')[0].split('#')[0]
                    
                    if self._is_valid_domain(domain):
                        urls.add(domain)
                except:
                    pass
        
        return urls

    def _is_valid_domain(self, domain):
        """Check if domain is valid"""
        if not domain or len(domain) < 4:
            return False
        
        # Must have dot
        if '.' not in domain:
            return False
        
        # Check for invalid characters
        if any(c in domain for c in [' ', '"', "'", '<', '>', '(', ')']):
            return False
        
        # Must have valid TLD
        parts = domain.split('.')
        if len(parts) < 2:
            return False
        
        tld = parts[-1].lower()
        if not tld.isalpha() or len(tld) < 2:
            return False
        
        return True

    def _is_valid_url(self, url):
        """Additional URL validation"""
        # Skip very short URLs
        if len(url) < 5:
            return False
        
        # Skip localhost/internal
        if any(x in url.lower() for x in ['localhost', '127.0.0.1', '0.0.0.0', '192.168']):
            return False
        
        return True

    def _is_ad_domain(self, url):
        """Check if URL is ad domain"""
        url_lower = url.lower()
        return any(ad in url_lower for ad in self.ad_domains)

    def _update_results(self, dt):
        """Update UI with results"""
        if not self.extracted_urls:
            self.results_label.text = 'No URLs found in APK'
            self.status_label.text = 'No URLs found'
            self.status_label.color = (1, 0.7, 0, 1)
        else:
            result_text = f'Found {len(self.extracted_urls)} URLs:\n\n'
            result_text += '\n'.join(self.extracted_urls)
            self.results_label.text = result_text
            self.status_label.text = f'Extracted {len(self.extracted_urls)} URLs!'
            self.status_label.color = (0.5, 1, 0.5, 1)
            self.save_btn.disabled = False
        
        self.extract_btn.disabled = False

    def _show_error(self, message):
        """Show error"""
        self.status_label.text = message
        self.status_label.color = (1, 0.3, 0.3, 1)
        self.results_label.text = f'Error occurred:\n{message}'
        self.extract_btn.disabled = False
        self.progress.value = 0

    def save_results(self, instance):
        """Save to file"""
        if not self.extracted_urls:
            return
        
        try:
            # Try multiple paths
            save_paths = [
                '/sdcard/Download/extracted_urls.txt',
                '/storage/emulated/0/Download/extracted_urls.txt',
                os.path.join(os.path.expanduser('~'), 'extracted_urls.txt')
            ]
            
            output_file = None
            for path in save_paths:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(f'APK URL Extractor Results\n')
                        f.write(f'Total URLs: {len(self.extracted_urls)}\n')
                        f.write('=' * 50 + '\n\n')
                        for url in self.extracted_urls:
                            f.write(url + '\n')
                    output_file = path
                    break
                except:
                    continue
            
            if output_file:
                self.status_label.text = f'Saved to {os.path.basename(output_file)}'
                self.status_label.color = (0.5, 1, 0.5, 1)
                
                popup = Popup(
                    title='Success!',
                    content=Label(text=f'Saved to:\n{output_file}'),
                    size_hint=(0.85, 0.35)
                )
                popup.open()
            else:
                raise Exception("Could not save to any path")
            
        except Exception as e:
            self.status_label.text = f'Save error: {str(e)}'
            self.status_label.color = (1, 0.3, 0.3, 1)


if __name__ == '__main__':
    URLExtractorApp().run()
