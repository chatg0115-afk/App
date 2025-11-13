"""
APK URL Extractor - Complete Working App
Save this as main.py in ~/url_extractor_app/
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
from androguard.core.bytecodes.apk import APK
import re
import threading
import os

# Set window background color
Window.clearcolor = (0.2, 0.3, 0.5, 1)


class GradientButton(Button):
    """Beautiful gradient button"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = (0, 0, 0, 0)
        self.background_normal = ''
        with self.canvas.before:
            Color(0.2, 0.5, 0.9, 1)
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[20])
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
            'appspot.com', 'unity3d.com', 'appsflyer', 'adjust.com'
        ]

    def build(self):
        # Main layout
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        
        # Header
        header = Label(
            text='[b]🚀 APK URL Extractor[/b]',
            markup=True,
            size_hint_y=0.1,
            font_size='24sp',
            color=(1, 1, 1, 1)
        )
        layout.add_widget(header)
        
        # Subtitle
        subtitle = Label(
            text='Extract URLs • Filter Ads • Save Results',
            size_hint_y=0.05,
            font_size='14sp',
            color=(0.7, 0.9, 1, 1)
        )
        layout.add_widget(subtitle)
        
        # Select APK button
        self.select_btn = GradientButton(
            text='📁 Select APK File',
            size_hint_y=0.1,
            font_size='18sp',
            bold=True
        )
        self.select_btn.bind(on_press=self.select_apk)
        layout.add_widget(self.select_btn)
        
        # Extract button
        self.extract_btn = GradientButton(
            text='⚡ Extract URLs',
            size_hint_y=0.1,
            font_size='18sp',
            bold=True,
            disabled=True
        )
        self.extract_btn.bind(on_press=self.extract_urls)
        layout.add_widget(self.extract_btn)
        
        # Progress bar
        self.progress = ProgressBar(max=100, size_hint_y=0.05)
        self.progress.value = 0
        layout.add_widget(self.progress)
        
        # Status label
        self.status_label = Label(
            text='Ready to extract URLs',
            size_hint_y=0.05,
            font_size='14sp',
            color=(0.5, 1, 0.5, 1)
        )
        layout.add_widget(self.status_label)
        
        # Results area
        scroll = ScrollView(size_hint_y=0.45)
        self.results_label = Label(
            text='URLs will appear here...',
            size_hint_y=None,
            font_size='12sp',
            color=(1, 1, 1, 1),
            halign='left',
            valign='top'
        )
        self.results_label.bind(
            texture_size=self.results_label.setter('size')
        )
        scroll.add_widget(self.results_label)
        layout.add_widget(scroll)
        
        # Save button
        self.save_btn = GradientButton(
            text='💾 Save Results',
            size_hint_y=0.1,
            font_size='18sp',
            bold=True,
            disabled=True
        )
        self.save_btn.bind(on_press=self.save_results)
        layout.add_widget(self.save_btn)
        
        return layout

    def select_apk(self, instance):
        """Open file chooser to select APK"""
        content = BoxLayout(orientation='vertical', spacing=10)
        
        # File chooser
        filechooser = FileChooserListView(
            filters=['*.apk'],
            path='/sdcard'
        )
        content.add_widget(filechooser)
        
        # Buttons
        btn_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        select_button = Button(text='Select', size_hint_x=0.5)
        cancel_button = Button(text='Cancel', size_hint_x=0.5)
        
        btn_layout.add_widget(select_button)
        btn_layout.add_widget(cancel_button)
        content.add_widget(btn_layout)
        
        # Create popup
        popup = Popup(
            title='Choose APK File',
            content=content,
            size_hint=(0.9, 0.9)
        )
        
        def on_select(btn):
            if filechooser.selection:
                self.selected_apk = filechooser.selection[0]
                filename = os.path.basename(self.selected_apk)
                self.select_btn.text = f'✓ {filename[:25]}...'
                self.extract_btn.disabled = False
                self.status_label.text = 'APK selected! Ready to extract.'
                self.status_label.color = (0.5, 1, 0.5, 1)
            popup.dismiss()
        
        select_button.bind(on_press=on_select)
        cancel_button.bind(on_press=popup.dismiss)
        
        popup.open()

    def extract_urls(self, instance):
        """Extract URLs from selected APK"""
        if not self.selected_apk:
            return
        
        self.extract_btn.disabled = True
        self.status_label.text = 'Extracting URLs...'
        self.status_label.color = (1, 1, 0, 1)
        self.progress.value = 0
        
        # Run extraction in separate thread
        thread = threading.Thread(target=self._extract_worker)
        thread.start()

    def _extract_worker(self):
        """Worker thread for URL extraction"""
        try:
            # Update progress
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 20), 0)
            
            # Load APK
            apk = APK(self.selected_apk)
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 40), 0)
            
            # Extract URLs from various sources
            urls_set = set()
            
            # From manifest
            manifest = apk.get_android_manifest_xml()
            urls_set.update(self._extract_urls_from_text(str(manifest)))
            
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 60), 0)
            
            # From resources
            for file in apk.get_files():
                if file.endswith(('.xml', '.json', '.txt')):
                    try:
                        content = apk.get_file(file).decode('utf-8', errors='ignore')
                        urls_set.update(self._extract_urls_from_text(content))
                    except:
                        pass
            
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 80), 0)
            
            # Filter ads
            filtered_urls = [url for url in urls_set if not self._is_ad_domain(url)]
            self.extracted_urls = sorted(filtered_urls)
            
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 100), 0)
            
            # Update UI
            Clock.schedule_once(self._update_results, 0)
            
        except Exception as e:
            Clock.schedule_once(
                lambda dt: self._show_error(f'Error: {str(e)}'), 0
            )

    def _extract_urls_from_text(self, text):
        """Extract URLs from text using regex"""
        url_pattern = r'https?://[^\s"\'<>)}\]]+|(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s"\'<>)}\]]*'
        matches = re.findall(url_pattern, text, re.IGNORECASE)
        
        urls = set()
        for match in matches:
            try:
                # Clean and extract domain
                cleaned = re.sub(r'^https?://', '', match)
                cleaned = re.sub(r'^www\.', '', cleaned)
                domain = cleaned.split('/')[0].split('?')[0]
                if '.' in domain and len(domain) > 4:
                    urls.add(domain)
            except:
                pass
        
        return urls

    def _is_ad_domain(self, url):
        """Check if URL is an ad domain"""
        url_lower = url.lower()
        return any(ad in url_lower for ad in self.ad_domains)

    def _update_results(self, dt):
        """Update results in UI"""
        if not self.extracted_urls:
            self.results_label.text = 'No URLs found!'
            self.status_label.text = 'No URLs found in APK'
            self.status_label.color = (1, 0.5, 0, 1)
        else:
            result_text = f'[b]Found {len(self.extracted_urls)} URLs (Ads Filtered)[/b]\n\n'
            result_text += '\n'.join(self.extracted_urls)
            self.results_label.text = result_text
            self.status_label.text = f'✓ Extracted {len(self.extracted_urls)} URLs!'
            self.status_label.color = (0.5, 1, 0.5, 1)
            self.save_btn.disabled = False
        
        self.extract_btn.disabled = False

    def _show_error(self, message):
        """Show error message"""
        self.status_label.text = message
        self.status_label.color = (1, 0, 0, 1)
        self.extract_btn.disabled = False
        self.progress.value = 0

    def save_results(self, instance):
        """Save results to file"""
        if not self.extracted_urls:
            return
        
        try:
            output_file = '/sdcard/Download/extracted_urls.txt'
            with open(output_file, 'w') as f:
                for url in self.extracted_urls:
                    f.write(url + '\n')
            
            self.status_label.text = f'✓ Saved to {output_file}'
            self.status_label.color = (0.5, 1, 0.5, 1)
            
            # Show success popup
            popup = Popup(
                title='Success!',
                content=Label(text=f'File saved:\n{output_file}'),
                size_hint=(0.8, 0.3)
            )
            popup.open()
            
        except Exception as e:
            self.status_label.text = f'Error saving: {str(e)}'
            self.status_label.color = (1, 0, 0, 1)


def run_app():
    URLExtractorApp().run()