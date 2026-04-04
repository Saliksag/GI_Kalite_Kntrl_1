import sys
import math
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QInputDialog, QMessageBox, QFrame)
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QRect, QPoint

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Kalite Kontrol Sistemi - Ölçüm Yazılımı")
        self.setGeometry(100, 100, 1200, 800)

        # Temel Değişkenler
        self.image_path = None
        self.original_image = None
        self.display_image = None # Ekranda gösterilen (Çizim vs yapılmış hali)
        
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_drawing = False
        self.roi_rect = QRect()

        self.pixel_per_mm = 1.0 # Varsayılan piksel / mm oranı
        self.calibration_done = False # Referans ölçüm yapıldı mı?

        # Arayüz Kurulumu
        self.initUI()

    def initUI(self):
        # Ana Widget ve Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)

        # --- SOL PANEL (Butonlar) ---
        left_panel = QFrame()
        left_panel.setFixedWidth(250)
        left_panel.setFrameShape(QFrame.StyledPanel)
        left_vbox = QVBoxLayout()
        left_panel.setLayout(left_vbox)

        # Durum Etiketi
        self.status_label = QLabel("Durum: Seçim Bekleniyor")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-weight: bold; color: blue;")
        
        # Butonlar
        self.btn_load_image = QPushButton("Dosya Seç")
        self.btn_load_image.setMinimumHeight(50)
        self.btn_load_image.clicked.connect(self.load_image)

        self.btn_reference = QPushButton("Referans Ölçü Al (Daire Bul)")
        self.btn_reference.setMinimumHeight(50)
        self.btn_reference.setEnabled(False)
        self.btn_reference.clicked.connect(self.set_reference)

        self.btn_measure = QPushButton("Ölçüm Yap (Daire Bul)")
        self.btn_measure.setMinimumHeight(50)
        self.btn_measure.setEnabled(False)
        self.btn_measure.clicked.connect(self.measure_part)

        left_vbox.addWidget(self.status_label)
        left_vbox.addSpacing(20)
        left_vbox.addWidget(self.btn_load_image)
        left_vbox.addWidget(self.btn_reference)
        left_vbox.addWidget(self.btn_measure)
        left_vbox.addStretch()

        # Kalibrasyon Bilgi Paneli
        self.lbl_calib_info = QLabel(f"Piksel/mm Oranı: Belirlenmedi")
        self.lbl_calib_info.setWordWrap(True)
        left_vbox.addWidget(self.lbl_calib_info)

        # --- SAĞ PANEL (Resim Gösterme Tuvali) ---
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #2e2e2e;") # Arka plan rengi (Dark mode havası)
        
        # Orijinal QLabel özelliklerini kullanarak çizim işlemlerini yakalayacağız
        self.image_label.mousePressEvent = self.mousePressEvent_image
        self.image_label.mouseMoveEvent = self.mouseMoveEvent_image
        self.image_label.mouseReleaseEvent = self.mouseReleaseEvent_image

        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.image_label)

    # --- DOSYA VE YÜKLEME İŞLEMLERİ ---
    def load_image(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Resim Seç", "", "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp)", options=options)
        if file_name:
            self.image_path = file_name
            self.original_image = cv2.imread(self.image_path)
            
            if self.original_image is None:
                QMessageBox.critical(self, "Hata", "Resim yüklenemedi!")
                return
                
            self.original_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB) # OpenCV BGR, PyQt RGB kullanır
            
            self.status_label.setText("Durum: Resim Yüklendi. Fareyle alan seçin.")
            self.btn_reference.setEnabled(True)
            self.btn_measure.setEnabled(self.calibration_done)
            self.roi_rect = QRect() # Önceki seçimleri sıfırla
            self.update_image_display(self.original_image.copy())

    def update_image_display(self, img_array, draw_roi=False):
        """ Numpy matrisini (resmi) QPixmap yapıp ekranda gösterir. """
        h, w, ch = img_array.shape
        bytes_per_line = ch * w
        q_img = QImage(img_array.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        
        # Resim boyutları Label'ı aşarsa küçült
        lbl_w = self.image_label.width()
        lbl_h = self.image_label.height()
        
        # Orantılı küçültme bilgisi (Ekranda gösterilen ile gerçek piksel eşlemesi için gerekli olacak)
        self.scaled_pixmap = pixmap.scaled(lbl_w, lbl_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.scale_ratio_w = w / self.scaled_pixmap.width()
        self.scale_ratio_h = h / self.scaled_pixmap.height()
        self.offset_x = (lbl_w - self.scaled_pixmap.width()) // 2
        self.offset_y = (lbl_h - self.scaled_pixmap.height()) // 2

        # Eğer fare ile çizgi taranıyorsa üstüne o yeşil kutuyu çizdirelim
        if draw_roi and not self.roi_rect.isNull():
            painter = QPainter(self.scaled_pixmap)
            painter.setPen(QPen(QColor(0, 255, 0), 2, Qt.SolidLine))
            # Offset olmadan doğrudan pixmap üzerine çiziyoruz
            painter.drawRect(self.roi_rect)
            painter.end()

        self.image_label.setPixmap(self.scaled_pixmap)
        
    # --- FARE (MOUSE) OLAYLARI (ROI SEÇİMİ İÇİN) ---
    def mousePressEvent_image(self, event):
        if event.button() == Qt.LeftButton and self.original_image is not None:
            # Tıklanılan noktanın label offsetine göre düzeltilmiş hali
            x = event.pos().x() - self.offset_x
            y = event.pos().y() - self.offset_y
            
            # Seçim alanına (pixmap dışına) tıkladıysa engelle
            if x < 0 or y < 0 or x >= self.scaled_pixmap.width() or y >= self.scaled_pixmap.height():
                return
            
            self.is_drawing = True
            self.start_point = QPoint(x, y)
            self.end_point = self.start_point
            
    def mouseMoveEvent_image(self, event):
        if self.is_drawing:
            x = event.pos().x() - self.offset_x
            y = event.pos().y() - self.offset_y
            # Piksel dışına taşmaları sınırla
            x = max(0, min(x, self.scaled_pixmap.width()))
            y = max(0, min(y, self.scaled_pixmap.height()))
            
            self.end_point = QPoint(x, y)
            self.roi_rect = QRect(self.start_point, self.end_point).normalized()
            self.update_image_display(self.original_image.copy(), draw_roi=True)
            
    def mouseReleaseEvent_image(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            if self.roi_rect.width() > 10 and self.roi_rect.height() > 10:
                self.status_label.setText("Durum: Alan seçildi. Şimdi Buton ile ölçülebilir.")

    # --- ÖLÇÜM VE MANTIK ALGORİTMASI ---
    def process_circle_detection(self):
        """ Seçili alanı keser, hassas daire analizi (Sub-pixel, Ellipse Fit) yapar ve çizer """
        if self.roi_rect.isNull() or self.roi_rect.width() < 10 or self.original_image is None:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce fareyle geçerli bir alan seçin!")
            return None, None

        # Ekranda çizdiğimiz kutunun gerçek fotodaki pixelleri (Orantıyı düzeltiyoruz)
        real_x = int(self.roi_rect.x() * self.scale_ratio_w)
        real_y = int(self.roi_rect.y() * self.scale_ratio_h)
        real_w = int(self.roi_rect.width() * self.scale_ratio_w)
        real_h = int(self.roi_rect.height() * self.scale_ratio_h)

        # Görseli kırma (Crop)
        cropped_img = self.original_image[real_y:real_y+real_h, real_x:real_x+real_w]

        # 1. Gri Tönalite ve Bilateral Filter
        gray = cv2.cvtColor(cropped_img, cv2.COLOR_RGB2GRAY)
        # GaussianBlur veya MedianBlur yerine kenarları koruyup pürüzleri gideren Bilateral kullanıyoruz.
        # Kullanıcı isteğiyle d=6 yapıldı (Komşuluk piksel çapı daraltıldı)
        filtered = cv2.bilateralFilter(gray, d=6, sigmaColor=75, sigmaSpace=75)

        # 2. Canny Kenar Algılama (Otsu Yöntemi ile Otomatik Alt-Üst Threshold hesaplama)
        high_thresh, _ = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        low_thresh = 0.5 * high_thresh
        edges = cv2.Canny(filtered, low_thresh, high_thresh)

        # 3. Kontur Analizi
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        
        best_contour = None
        best_circularity = 0.0
        min_perimeter = 50 # Çok küçük gürültüleri es geç

        for cnt in contours:
            perimeter = cv2.arcLength(cnt, True)
            if perimeter < min_perimeter:
                continue
            
            area = cv2.contourArea(cnt)
            # Matematiksel Dairesellik Oranı (Circularity = 4 * PI * Area / Perimeter^2)
            # Mükemmel bir dairenin değeri 1.0 civarındadır.
            if perimeter > 0:
                circularity = 4 * math.pi * (area / (perimeter * perimeter))
                if circularity > best_circularity:
                    best_circularity = circularity
                    best_contour = cnt

        # En az 5 nokta gerekli çünkü elips matematiksel olarak 5 noktadan geçer
        if best_contour is not None and len(best_contour) >= 5:
            # 4. Alt-Piksel Kenar Rafine Etme (Sub-pixel Refinement)
            # Normal vektörlerini dikkate alarak gradyanın zirve noktasına göre alt-piksel offseti atıyoruz.
            grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            
            subpixel_pts = []
            max_offset = 1.0 # En fazla 1 piksel kadar kaydırma yap (güvenlik sınırı)
            
            for pt in best_contour:
                x, y = pt[0][0], pt[0][1]
                
                # Kenarlara çok yakınsa offset deneme, hata verbilir
                if x <= 1 or x >= real_w - 2 or y <= 1 or y >= real_h - 2:
                    subpixel_pts.append([float(x), float(y)])
                    continue
                
                gx = grad_x[y, x]
                gy = grad_y[y, x]
                norm = math.hypot(gx, gy)
                
                if norm == 0:
                    subpixel_pts.append([float(x), float(y)])
                    continue
                
                nx, ny = gx / norm, gy / norm
                
                # Gradyan yönündeki piksellerde (geriye 1, ileri 1) parabolik tepe bulma
                x1, y1 = int(round(x - nx)), int(round(y - ny))
                x2, y2 = int(round(x + nx)), int(round(y + ny))
                
                # Sınır güvenlik kontrolü
                if x1 < 0 or x1 >= real_w or y1 < 0 or y1 >= real_h or \
                   x2 < 0 or x2 >= real_w or y2 < 0 or y2 >= real_h:
                    subpixel_pts.append([float(x), float(y)])
                    continue
                    
                m1 = math.hypot(grad_x[y1, x1], grad_y[y1, x1])
                m0 = norm # Merkez pikselin gradyan büyüklüğü
                m2 = math.hypot(grad_x[y2, x2], grad_y[y2, x2])
                
                denom = m1 - 2*m0 + m2
                offset = 0.0
                if denom != 0:
                    offset = 0.5 * (m1 - m2) / denom
                
                # Offset sınırla
                offset = max(min(offset, max_offset), -max_offset)
                
                # Gerçek matematiksel nokta koordinatı
                new_x = float(x) + offset * nx
                new_y = float(y) + offset * ny
                subpixel_pts.append([new_x, new_y])
                
            subpixel_pts_np = np.array(subpixel_pts, dtype=np.float32)

            # 5. Direct Ellipse Fitting
            # cv2 sürümüne göre fitEllipseDirect veya düz fitEllipse kullan
            try:
                ellipse = cv2.fitEllipseDirect(subpixel_pts_np)
            except AttributeError:
                # OpenCV çok skiyse fallback
                ellipse = cv2.fitEllipse(subpixel_pts_np)
                
            (center, axes, angle) = ellipse
            
            # axes tuple'ında major_axis (uzun) ve minor_axis (kısa) tutulur
            major_axis = max(axes[0], axes[1])
            minor_axis = min(axes[0], axes[1])
            
            # 6. Daire Doğrulaması (Validation)
            # Uzun çap ile kısa çap arasındaki fark %2'den (0.02) büyükse daire değildir.
            if major_axis == 0:
                QMessageBox.warning(self, "Hata", "Elips eksenleri 0 döndü. Lütfen farklı alan seçin.")
                return None, None
                
            diff_ratio = (major_axis - minor_axis) / major_axis
            if diff_ratio > 0.05: # Toleransı biraz geniş tuttuk (%5). Özel isteğe göre 0.02 %2'ye çekilebilir.
                QMessageBox.warning(self, "Hata", f"Seçilen alan tam dairesel değil. (Sapma: %{diff_ratio*100:.1f}) Lütfen daha düz veya gölgesiz bir alan seçin.")
                return None, None
            
            # Ortalama çap hesabı
            avg_diameter_px = (major_axis + minor_axis) / 2.0
            
            # Orijinal resme göre offset aktarımları
            main_cx = center[0] + real_x
            main_cy = center[1] + real_y
            
            # Çizim ve Görsel Geri Bildirim
            display_img = self.original_image.copy()
            
            # Fit edilen elipsi (kırmızı çizgilerle) orijinal fotoğrafa çiz (Axes yarıçaptır, bu yüzden /2)
            cv2.ellipse(display_img, 
                        (int(main_cx), int(main_cy)), 
                        (int(axes[0]/2), int(axes[1]/2)), 
                        angle, 0, 360, (0, 0, 255), 2)
            
            # Ortasına operatörün referans alması için "+" artı işareti çiz
            cross_s = 15
            cv2.line(display_img, (int(main_cx) - cross_s, int(main_cy)), (int(main_cx) + cross_s, int(main_cy)), (0, 0, 255), 2)
            cv2.line(display_img, (int(main_cx), int(main_cy) - cross_s), (int(main_cx), int(main_cy) + cross_s), (0, 0, 255), 2)
            
            self.update_image_display(display_img)
            return avg_diameter_px, display_img
        else:
            QMessageBox.warning(self, "Bulunamadı", "Seçtiğiniz alanda tutarlı bir dairesel kenar bulunamadı.")
            return None, None

    def set_reference(self):
        """ Mastarı ölçüp, referans kalibrasyonu (Piksel/mm) çıkarır """
        avg_px, _ = self.process_circle_detection()
        
        if avg_px is not None:
            # Kullanıcıdan mm değerini (Mastar Çapını) isteyelim
            mm_val, ok = QInputDialog.getDouble(self, "Referans Değeri",
                                              "Mastar parçasının iç çapı kaç milimetre (mm)?",
                                              20.0, 0.1, 1000.0, 2)
            if ok:
                self.pixel_per_mm = avg_px / mm_val
                self.calibration_done = True
                self.btn_measure.setEnabled(True)
                
                text = f"Başarılı! \nBulunan Çap: {avg_px:.2f} Piksel\nVerilen Çap: {mm_val} mm\nOran: 1 mm = {self.pixel_per_mm:.2f} Piksel"
                self.lbl_calib_info.setText(text)
                self.status_label.setText("Durum: Referans Alındı.")
                QMessageBox.information(self, "Bilgi", text)
            else:
                 # Temizle eğer iptal edilmişse
                 self.update_image_display(self.original_image.copy(), draw_roi=True)

    def measure_part(self):
        """ Önceden kaydedilmiş piksel/mm oranını kullanarak yeni resmi ölçer """
        if not self.calibration_done:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce 'Referans Ölçü' alın.")
            return

        avg_px, display_img = self.process_circle_detection()
        if avg_px is not None and display_img is not None:
             # mm = Piksel / Oran
             mm_result = avg_px / self.pixel_per_mm
             
             # Resmin üzerine yazma işlemi
             text = f"TESPIT EDILEN CAP: {mm_result:.2f} mm"
             
             # process_circle_detection'dan gelen çizimli resmin (kırmızı elipsli) üstüne yazdır
             cv2.putText(display_img, text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 5)
             
             self.update_image_display(display_img)
             self.status_label.setText(f"Durum: Ölçüm Tamamlandı. Çap = {mm_result:.2f} mm")
             QMessageBox.information(self, "Ölçüm Sonucu", f"Parça Çapı ortalama: {mm_result:.2f} mm olarak hesaplandı.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Tasarım İçin Basit StyleSheet
    app.setStyleSheet("""
        QMainWindow { background-color: #f0f0f0; }
        QPushButton { font-size: 14px; font-weight: bold; background-color: #0078D7; color: white; border-radius: 5px; }
        QPushButton:hover { background-color: #005A9E; }
        QPushButton:disabled { background-color: #cccccc; color: #666666; }
        QLabel { font-size: 14px; }
    """)
    ex = MainApp()
    ex.show()
    sys.exit(app.exec_())
