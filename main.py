import sys
import math
import json
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QInputDialog, QMessageBox, QFrame, QGroupBox)
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QRect, QPoint


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Kalite Kontrol Sistemi - Endüstriyel Ölçüm Yazılımı")
        self.setGeometry(100, 100, 1200, 800)

        # ── Temel Değişkenler ──
        self.image_path = None
        self.original_image = None      # Yüklenen ham görüntü (RGB)
        self.corrected_image = None     # Lens + Perspektif düzeltmesi uygulanmış görüntü

        self.start_point_orig = QPoint()  # ROI başlangıç noktası (orijinal koordinat)
        self.end_point_orig = QPoint()    # ROI bitiş noktası (orijinal koordinat)
        self.is_drawing = False
        self.roi_rect = QRect()           # Orijinal görüntü koordinatlarında ROI

        self.pixel_per_mm = 1.0
        self.calibration_done = False

        # ── Lens Kalibrasyonu Değişkenleri ──
        self.camera_matrix = None
        self.dist_coeffs = None
        self.lens_calibration_done = False

        # ── Perspektif Kalibrasyonu Değişkenleri ──
        self.perspective_matrix = None
        self.perspective_calibration_done = False
        self.perspective_points = []       # Kullanıcının seçtiği 4 nokta
        self.selecting_perspective = False  # Perspektif nokta seçim modu aktif mi
        self.perspective_ref_size_mm = 0.0  # Referans karenin kenar uzunluğu (mm)

        # ── Scale / offset bilgileri (başlangıç) ──
        self.scale_ratio_w = 1.0
        self.scale_ratio_h = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.scaled_pixmap = None

        # Arayüz Kurulumu
        self.initUI()

        # Kaydedilmiş kalibrasyon verisini oku
        self._load_calibration_data()

    # ═══════════════════════════════════════════════════════════════
    #  ARAYÜZ
    # ═══════════════════════════════════════════════════════════════
    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)

        # ── SOL PANEL (Butonlar) ──
        left_panel = QFrame()
        left_panel.setFixedWidth(280)
        left_panel.setFrameShape(QFrame.StyledPanel)
        left_vbox = QVBoxLayout()
        left_panel.setLayout(left_vbox)

        # Durum Etiketi
        self.status_label = QLabel("Durum: Seçim Bekleniyor")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-weight: bold; color: blue;")

        # Dosya Seç Butonu
        self.btn_load_image = QPushButton("📁  Dosya Seç")
        self.btn_load_image.setMinimumHeight(50)
        self.btn_load_image.clicked.connect(self.load_image)

        # ── Kalibrasyon Grubu ──
        calib_group = QGroupBox("Kalibrasyon")
        calib_vbox = QVBoxLayout()
        calib_group.setLayout(calib_vbox)

        self.btn_lens_calib = QPushButton("🔍  Lens Kalibrasyonu\n(Satranç Tahtası)")
        self.btn_lens_calib.setMinimumHeight(50)
        self.btn_lens_calib.clicked.connect(self.calibrate_lens)

        self.btn_perspective_calib = QPushButton("📐  Perspektif Kalibrasyonu\n(4 Nokta)")
        self.btn_perspective_calib.setMinimumHeight(50)
        self.btn_perspective_calib.setEnabled(False)
        self.btn_perspective_calib.clicked.connect(self.start_perspective_calibration)

        self.btn_reference = QPushButton("📏  Referans Ölçü Al (Daire Bul)")
        self.btn_reference.setMinimumHeight(50)
        self.btn_reference.setEnabled(False)
        self.btn_reference.clicked.connect(self.set_reference)

        calib_vbox.addWidget(self.btn_lens_calib)
        calib_vbox.addWidget(self.btn_perspective_calib)
        calib_vbox.addWidget(self.btn_reference)

        # ── Ölçüm Grubu ──
        measure_group = QGroupBox("Ölçüm")
        measure_vbox = QVBoxLayout()
        measure_group.setLayout(measure_vbox)

        self.btn_measure = QPushButton("⚙️  Ölçüm Yap (Daire Bul)")
        self.btn_measure.setMinimumHeight(50)
        self.btn_measure.setEnabled(False)
        self.btn_measure.clicked.connect(self.measure_part)

        measure_vbox.addWidget(self.btn_measure)

        # ── Sıfırlama Butonu ──
        self.btn_reset_calib = QPushButton("🗑️  Kalibrasyonları Sıfırla")
        self.btn_reset_calib.setMinimumHeight(35)
        self.btn_reset_calib.clicked.connect(self.reset_calibrations)

        # ── Sol panel düzeni ──
        left_vbox.addWidget(self.status_label)
        left_vbox.addSpacing(10)
        left_vbox.addWidget(self.btn_load_image)
        left_vbox.addSpacing(10)
        left_vbox.addWidget(calib_group)
        left_vbox.addSpacing(10)
        left_vbox.addWidget(measure_group)
        left_vbox.addSpacing(10)
        left_vbox.addWidget(self.btn_reset_calib)
        left_vbox.addStretch()

        # Kalibrasyon durumu etiketleri
        self.lbl_lens_status = QLabel("Lens Kalibrasyonu: ❌ Yapılmadı")
        self.lbl_lens_status.setWordWrap(True)
        self.lbl_perspective_status = QLabel("Perspektif Kalibrasyonu: ❌ Yapılmadı")
        self.lbl_perspective_status.setWordWrap(True)
        self.lbl_calib_info = QLabel("Piksel/mm Oranı: Belirlenmedi")
        self.lbl_calib_info.setWordWrap(True)

        left_vbox.addWidget(self.lbl_lens_status)
        left_vbox.addWidget(self.lbl_perspective_status)
        left_vbox.addWidget(self.lbl_calib_info)

        # ── SAĞ PANEL (Resim Tuvali) ──
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #2e2e2e;")

        self.image_label.mousePressEvent = self.mousePressEvent_image
        self.image_label.mouseMoveEvent = self.mouseMoveEvent_image
        self.image_label.mouseReleaseEvent = self.mouseReleaseEvent_image

        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.image_label)

    # ═══════════════════════════════════════════════════════════════
    #  KALİBRASYON VERİSİ KAYIT / YÜKLEME  (JSON)
    # ═══════════════════════════════════════════════════════════════
    def _calibration_file_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "calibration_data.json")

    def _save_calibration_data(self):
        data = {}
        if self.lens_calibration_done and self.camera_matrix is not None:
            data["camera_matrix"] = self.camera_matrix.tolist()
            data["dist_coeffs"] = self.dist_coeffs.tolist()
        if self.perspective_calibration_done and self.perspective_matrix is not None:
            data["perspective_matrix"] = self.perspective_matrix.tolist()
            data["perspective_ref_size_mm"] = self.perspective_ref_size_mm
        if self.calibration_done:
            data["pixel_per_mm"] = self.pixel_per_mm
        try:
            with open(self._calibration_file_path(), 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Kalibrasyon kayıt hatası: {e}")

    def _load_calibration_data(self):
        path = self._calibration_file_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r') as f:
                data = json.load(f)

            if "camera_matrix" in data:
                self.camera_matrix = np.array(data["camera_matrix"], dtype=np.float64)
                self.dist_coeffs = np.array(data["dist_coeffs"], dtype=np.float64)
                self.lens_calibration_done = True
                self.lbl_lens_status.setText("Lens Kalibrasyonu: ✅ Yüklendi")

            if "perspective_matrix" in data:
                self.perspective_matrix = np.array(data["perspective_matrix"],
                                                   dtype=np.float64)
                self.perspective_ref_size_mm = data.get("perspective_ref_size_mm", 0.0)
                self.perspective_calibration_done = True
                self.lbl_perspective_status.setText("Perspektif Kalibrasyonu: ✅ Yüklendi")

            if "pixel_per_mm" in data:
                self.pixel_per_mm = data["pixel_per_mm"]
                self.calibration_done = True
                self.lbl_calib_info.setText(
                    f"Piksel/mm Oranı: {self.pixel_per_mm:.2f}")
                self.btn_measure.setEnabled(True)

        except Exception as e:
            print(f"Kalibrasyon yükleme hatası: {e}")

    def reset_calibrations(self):
        reply = QMessageBox.question(
            self, "Onay",
            "Tüm kalibrasyon verilerini sıfırlamak istediğinize emin misiniz?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.camera_matrix = None
        self.dist_coeffs = None
        self.lens_calibration_done = False
        self.perspective_matrix = None
        self.perspective_calibration_done = False
        self.perspective_points = []
        self.pixel_per_mm = 1.0
        self.calibration_done = False

        self.lbl_lens_status.setText("Lens Kalibrasyonu: ❌ Yapılmadı")
        self.lbl_perspective_status.setText("Perspektif Kalibrasyonu: ❌ Yapılmadı")
        self.lbl_calib_info.setText("Piksel/mm Oranı: Belirlenmedi")
        self.btn_measure.setEnabled(False)

        path = self._calibration_file_path()
        if os.path.exists(path):
            os.remove(path)

        # Eğer resim yüklüyse düzeltmeyi geri al
        if self.original_image is not None:
            self.corrected_image = self.original_image.copy()
            self.update_image_display(self.corrected_image.copy())

        self.status_label.setText("Durum: Tüm kalibrasyonlar sıfırlandı.")

    # ═══════════════════════════════════════════════════════════════
    #  DOSYA VE YÜKLEME İŞLEMLERİ
    # ═══════════════════════════════════════════════════════════════
    def load_image(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Resim Seç", "",
            "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp)", options=options)
        if not file_name:
            return

        self.image_path = file_name
        self.original_image = cv2.imread(self.image_path)

        if self.original_image is None:
            QMessageBox.critical(self, "Hata", "Resim yüklenemedi!")
            return

        self.original_image = cv2.cvtColor(self.original_image, cv2.COLOR_BGR2RGB)

        # Lens + Perspektif düzeltmelerini uygula
        self.corrected_image = self._apply_corrections(self.original_image)

        self.status_label.setText("Durum: Resim Yüklendi. Fareyle alan seçin.")
        self.btn_reference.setEnabled(True)
        self.btn_perspective_calib.setEnabled(True)
        self.btn_measure.setEnabled(self.calibration_done)
        self.roi_rect = QRect()
        self.update_image_display(self.corrected_image.copy())

    def _apply_corrections(self, image):
        """Lens distorsiyon ve perspektif düzeltmelerini sırayla uygular."""
        result = image.copy()

        # 1. Lens distorsiyonu düzeltme
        if self.lens_calibration_done and self.camera_matrix is not None:
            h, w = result.shape[:2]
            new_cam_mtx, roi = cv2.getOptimalNewCameraMatrix(
                self.camera_matrix, self.dist_coeffs, (w, h), 1, (w, h))
            result = cv2.undistort(result, self.camera_matrix,
                                  self.dist_coeffs, None, new_cam_mtx)
            rx, ry, rw, rh = roi
            if rw > 0 and rh > 0:
                result = result[ry:ry + rh, rx:rx + rw]

        # 2. Perspektif düzeltme
        if self.perspective_calibration_done and self.perspective_matrix is not None:
            h, w = result.shape[:2]
            result = cv2.warpPerspective(result, self.perspective_matrix, (w, h))

        return result

    # ═══════════════════════════════════════════════════════════════
    #  GÖRÜNTÜ GÖSTERME
    # ═══════════════════════════════════════════════════════════════
    def update_image_display(self, img_array, draw_roi=False):
        """Numpy matrisini QPixmap yapıp ekranda gösterir."""
        h, w, ch = img_array.shape
        bytes_per_line = ch * w
        q_img = QImage(img_array.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)

        lbl_w = self.image_label.width()
        lbl_h = self.image_label.height()

        self.scaled_pixmap = pixmap.scaled(
            lbl_w, lbl_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.scale_ratio_w = w / self.scaled_pixmap.width()
        self.scale_ratio_h = h / self.scaled_pixmap.height()
        self.offset_x = (lbl_w - self.scaled_pixmap.width()) // 2
        self.offset_y = (lbl_h - self.scaled_pixmap.height()) // 2

        # ROI kutusunu çiz (orijinal → scaled koordinatlara dönüştür)
        if draw_roi and not self.roi_rect.isNull():
            painter = QPainter(self.scaled_pixmap)
            painter.setPen(QPen(QColor(0, 255, 0), 2, Qt.SolidLine))
            scaled_roi = QRect(
                int(self.roi_rect.x() / self.scale_ratio_w),
                int(self.roi_rect.y() / self.scale_ratio_h),
                int(self.roi_rect.width() / self.scale_ratio_w),
                int(self.roi_rect.height() / self.scale_ratio_h))
            painter.drawRect(scaled_roi)
            painter.end()

        # Perspektif kalibrasyonu sırasında seçilen noktaları çiz
        if self.selecting_perspective and len(self.perspective_points) > 0:
            painter = QPainter(self.scaled_pixmap)
            painter.setPen(QPen(QColor(255, 255, 0), 3, Qt.SolidLine))
            for i, pt in enumerate(self.perspective_points):
                sx = int(pt[0] / self.scale_ratio_w)
                sy = int(pt[1] / self.scale_ratio_h)
                painter.drawEllipse(QPoint(sx, sy), 8, 8)
                painter.drawText(sx + 12, sy - 5, f"{i + 1}")
                if i > 0:
                    prev = self.perspective_points[i - 1]
                    px = int(prev[0] / self.scale_ratio_w)
                    py = int(prev[1] / self.scale_ratio_h)
                    painter.drawLine(px, py, sx, sy)
            if len(self.perspective_points) == 4:
                f0 = self.perspective_points[0]
                f3 = self.perspective_points[3]
                painter.drawLine(
                    int(f3[0] / self.scale_ratio_w),
                    int(f3[1] / self.scale_ratio_h),
                    int(f0[0] / self.scale_ratio_w),
                    int(f0[1] / self.scale_ratio_h))
            painter.end()

        self.image_label.setPixmap(self.scaled_pixmap)

    # ═══════════════════════════════════════════════════════════════
    #  FARE (MOUSE) OLAYLARI  ─  ROI & PERSPEKTİF NOKTA SEÇİMİ
    # ═══════════════════════════════════════════════════════════════
    def mousePressEvent_image(self, event):
        if event.button() != Qt.LeftButton or self.corrected_image is None:
            return
        if self.scaled_pixmap is None:
            return

        x = event.pos().x() - self.offset_x
        y = event.pos().y() - self.offset_y

        if x < 0 or y < 0 or x >= self.scaled_pixmap.width() or y >= self.scaled_pixmap.height():
            return

        # Orijinal koordinatlara dönüştür
        orig_x = int(x * self.scale_ratio_w)
        orig_y = int(y * self.scale_ratio_h)

        # ── Perspektif nokta seçim modu ──
        if self.selecting_perspective:
            self.perspective_points.append((orig_x, orig_y))
            self.status_label.setText(
                f"Durum: Perspektif noktası {len(self.perspective_points)}/4 seçildi.")
            self.update_image_display(self.corrected_image.copy())
            if len(self.perspective_points) >= 4:
                self._complete_perspective_calibration()
            return

        # ── Normal ROI seçim modu ──
        self.is_drawing = True
        self.start_point_orig = QPoint(orig_x, orig_y)
        self.end_point_orig = self.start_point_orig

    def mouseMoveEvent_image(self, event):
        if not self.is_drawing:
            return
        if self.scaled_pixmap is None:
            return

        x = event.pos().x() - self.offset_x
        y = event.pos().y() - self.offset_y

        x = max(0, min(x, self.scaled_pixmap.width() - 1))
        y = max(0, min(y, self.scaled_pixmap.height() - 1))

        orig_x = int(x * self.scale_ratio_w)
        orig_y = int(y * self.scale_ratio_h)

        self.end_point_orig = QPoint(orig_x, orig_y)
        self.roi_rect = QRect(self.start_point_orig, self.end_point_orig).normalized()
        self.update_image_display(self.corrected_image.copy(), draw_roi=True)

    def mouseReleaseEvent_image(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            if self.roi_rect.width() > 10 and self.roi_rect.height() > 10:
                self.status_label.setText(
                    "Durum: Alan seçildi. Şimdi Buton ile ölçülebilir.")

    # ═══════════════════════════════════════════════════════════════
    #  LENS KALİBRASYONU  (Satranç Tahtası - Otomatik Desen Algılama)
    # ═══════════════════════════════════════════════════════════════
    def calibrate_lens(self):
        """Satranç tahtası resim(ler)i ile lens distorsiyon kalibrasyonu yapar.
        Desen boyutunu otomatik algılar."""
        options = QFileDialog.Options()
        file_names, _ = QFileDialog.getOpenFileNames(
            self, "Satranç Tahtası Resim(ler)i Seç", "",
            "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp)", options=options)
        if not file_names:
            return

        self.status_label.setText("Durum: Satranç tahtası deseni aranıyor...")
        QApplication.processEvents()

        # Denenecek yaygın iç köşe desen boyutları
        common_patterns = [
            (9, 6), (8, 6), (7, 6), (7, 5), (6, 5), (6, 4),
            (5, 4), (5, 3), (10, 7), (11, 8), (8, 5), (9, 7), (4, 3)
        ]

        obj_points_list = []   # 3D dünya noktaları
        img_points_list = []   # 2D resim noktaları
        detected_size = None
        img_shape = None

        for fname in file_names:
            img = cv2.imread(fname)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img_shape = gray.shape[::-1]   # (w, h)

            found = False
            for pattern_size in common_patterns:
                ret, corners = cv2.findChessboardCorners(
                    gray, pattern_size,
                    cv2.CALIB_CB_ADAPTIVE_THRESH
                    + cv2.CALIB_CB_NORMALIZE_IMAGE
                    + cv2.CALIB_CB_FAST_CHECK)

                if ret:
                    detected_size = pattern_size
                    found = True

                    objp = np.zeros(
                        (pattern_size[0] * pattern_size[1], 3), np.float32)
                    objp[:, :2] = np.mgrid[
                        0:pattern_size[0],
                        0:pattern_size[1]].T.reshape(-1, 2)

                    criteria = (cv2.TERM_CRITERIA_EPS
                                + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                    corners_refined = cv2.cornerSubPix(
                        gray, corners, (11, 11), (-1, -1), criteria)

                    obj_points_list.append(objp)
                    img_points_list.append(corners_refined)
                    break

            if not found:
                QMessageBox.warning(
                    self, "Uyarı",
                    f"'{os.path.basename(fname)}' dosyasında desen bulunamadı.")

        if len(obj_points_list) == 0:
            QMessageBox.critical(
                self, "Hata",
                "Hiçbir resimde satranç tahtası deseni algılanamadı!\n"
                "Lütfen net ve düzgün bir satranç tahtası resmi kullanın.")
            self.status_label.setText("Durum: Lens kalibrasyonu başarısız.")
            return

        ret, self.camera_matrix, self.dist_coeffs, _, _ = cv2.calibrateCamera(
            obj_points_list, img_points_list, img_shape, None, None)

        if ret:
            self.lens_calibration_done = True
            self.lbl_lens_status.setText(
                f"Lens Kalibrasyonu: ✅ Yapıldı\n"
                f"(Desen: {detected_size[0]}x{detected_size[1]}, "
                f"Hata: {ret:.4f}px)")
            self.status_label.setText(
                f"Durum: Lens kalibrasyonu başarılı! "
                f"(Yeniden proj. hatası: {ret:.4f}px)")
            self._save_calibration_data()

            if self.original_image is not None:
                self.corrected_image = self._apply_corrections(self.original_image)
                self.update_image_display(self.corrected_image.copy())

            QMessageBox.information(
                self, "Başarılı",
                f"Lens kalibrasyonu tamamlandı!\n\n"
                f"Algılanan desen: {detected_size[0]}x{detected_size[1]}\n"
                f"Kullanılan resim: {len(obj_points_list)}\n"
                f"Projeksiyon hatası: {ret:.4f} piksel")
        else:
            QMessageBox.critical(self, "Hata",
                                 "Kamera kalibrasyonu hesaplanamadı.")
            self.status_label.setText("Durum: Lens kalibrasyonu başarısız.")

    # ═══════════════════════════════════════════════════════════════
    #  PERSPEKTİF KALİBRASYONU  (4 Nokta Homography - Kuş Bakışı)
    # ═══════════════════════════════════════════════════════════════
    def start_perspective_calibration(self):
        """4 noktalı perspektif düzeltme kalibrasyonunu başlatır."""
        if self.corrected_image is None:
            QMessageBox.warning(self, "Uyarı",
                                "Lütfen önce bir resim yükleyin!")
            return

        size_mm, ok = QInputDialog.getDouble(
            self, "Referans Kare Boyutu",
            "Zemindeki referans karenin kenar uzunluğu (mm):",
            100.0, 1.0, 10000.0, 2)
        if not ok:
            return

        self.perspective_ref_size_mm = size_mm
        self.perspective_points = []
        self.selecting_perspective = True

        self.status_label.setText(
            "Durum: Referans karenin 4 köşesini sırayla tıklayın\n"
            "(Sol-üst → Sağ-üst → Sağ-alt → Sol-alt)")

        QMessageBox.information(
            self, "Perspektif Kalibrasyonu",
            "Resim üzerindeki referans karenin 4 köşesini\n"
            "sırasıyla tıklayın:\n\n"
            "1. Sol-üst köşe\n"
            "2. Sağ-üst köşe\n"
            "3. Sağ-alt köşe\n"
            "4. Sol-alt köşe")

    def _complete_perspective_calibration(self):
        """4 nokta seçildikten sonra perspektif matrisini hesaplar."""
        self.selecting_perspective = False

        if len(self.perspective_points) != 4:
            QMessageBox.critical(self, "Hata", "4 nokta seçilemedi!")
            return

        src_pts = np.array(self.perspective_points, dtype=np.float32)

        # Kenar uzunluklarını hesapla
        w_top = np.linalg.norm(src_pts[1] - src_pts[0])
        w_bot = np.linalg.norm(src_pts[2] - src_pts[3])
        h_left = np.linalg.norm(src_pts[3] - src_pts[0])
        h_right = np.linalg.norm(src_pts[2] - src_pts[1])

        max_w = int(max(w_top, w_bot))
        max_h = int(max(h_left, h_right))
        side = max(max_w, max_h)

        # Merkezi koruyarak hedef noktaları oluştur
        cx = float(np.mean(src_pts[:, 0]))
        cy = float(np.mean(src_pts[:, 1]))
        half = side / 2.0

        dst_pts = np.array([
            [cx - half, cy - half],   # Sol-üst
            [cx + half, cy - half],   # Sağ-üst
            [cx + half, cy + half],   # Sağ-alt
            [cx - half, cy + half],   # Sol-alt
        ], dtype=np.float32)

        self.perspective_matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        self.perspective_calibration_done = True
        self.perspective_points = []

        self.lbl_perspective_status.setText("Perspektif Kalibrasyonu: ✅ Yapıldı")
        self.status_label.setText("Durum: Perspektif kalibrasyonu tamamlandı!")
        self._save_calibration_data()

        if self.original_image is not None:
            self.corrected_image = self._apply_corrections(self.original_image)
            self.update_image_display(self.corrected_image.copy())

        QMessageBox.information(self, "Başarılı",
                                "Perspektif düzeltmesi uygulandı!")

    # ═══════════════════════════════════════════════════════════════
    #  ANA ÖLÇÜM ALGORİTMASI  (process_circle_detection)
    # ═══════════════════════════════════════════════════════════════
    def process_circle_detection(self):
        """Seçili ROI alanında endüstriyel hassasiyette daire analizi yapar.

        Pipeline:
          1. ROI kırpma  (orijinal koordinatlarda, düzeltilmiş görüntüde)
          2. Gri tonlama  +  Bilateral Filter
          3. CLAHE  (parlak metal yüzey parlama bastırma)
          4. Otsu thresholding  +  Canny kenar algılama
          5. Morfolojik kapatma  (kopuk kenarları birleştir)
          6. Kontur analizi  →  en dairesel konturu bul
          7. Fallback: HoughCircles  (kontur bulunamazsa)
          8. Sub-pixel hassasiyet  (cv2.cornerSubPix)
          9. Direct Ellipse Fit
         10. Dinamik tolerans  (perspektif → %2, aksi halde %8)
         11. Çap  =  sadece major_axis (uzun eksen)
        """
        if (self.roi_rect.isNull()
                or self.roi_rect.width() < 10
                or self.corrected_image is None):
            QMessageBox.warning(self, "Uyarı",
                                "Lütfen önce fareyle geçerli bir alan seçin!")
            return None, None

        # ── 1. ROI kırpma (zaten orijinal koordinatlarda) ──
        real_x = self.roi_rect.x()
        real_y = self.roi_rect.y()
        real_w = self.roi_rect.width()
        real_h = self.roi_rect.height()

        img_h, img_w = self.corrected_image.shape[:2]
        real_x = max(0, min(real_x, img_w - 1))
        real_y = max(0, min(real_y, img_h - 1))
        real_w = min(real_w, img_w - real_x)
        real_h = min(real_h, img_h - real_y)

        cropped_img = self.corrected_image[real_y:real_y + real_h,
                                           real_x:real_x + real_w]

        # ── 2. Gri tonlama + Bilateral Filter ──
        gray = cv2.cvtColor(cropped_img, cv2.COLOR_RGB2GRAY)
        filtered = cv2.bilateralFilter(gray, d=6, sigmaColor=75, sigmaSpace=75)

        # ── 3. CLAHE (Contrast Limited Adaptive Histogram Equalization) ──
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        filtered = clahe.apply(filtered)

        # ── 4. Canny kenar algılama (Otsu ile otomatik threshold) ──
        high_thresh, _ = cv2.threshold(
            filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        low_thresh = 0.5 * high_thresh
        edges = cv2.Canny(filtered, low_thresh, high_thresh)

        # ── 5. Morfolojik kapatma (kopuk kenarları birleştir) ──
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        # ── 6. Kontur analizi ──
        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        best_contour = None
        best_circularity = 0.0
        min_perimeter = 50

        for cnt in contours:
            perimeter = cv2.arcLength(cnt, True)
            if perimeter < min_perimeter:
                continue
            area = cv2.contourArea(cnt)
            if perimeter > 0:
                circularity = 4 * math.pi * (area / (perimeter * perimeter))
                if circularity > best_circularity:
                    best_circularity = circularity
                    best_contour = cnt

        # ── 7. HoughCircles Fallback ──
        if best_contour is None or len(best_contour) < 5:
            circles = cv2.HoughCircles(
                filtered, cv2.HOUGH_GRADIENT, dp=1.2,
                minDist=max(1, min(real_w, real_h) // 2),
                param1=max(1, high_thresh),
                param2=30,
                minRadius=max(1, min(real_w, real_h) // 8),
                maxRadius=max(1, min(real_w, real_h) // 2))

            if circles is not None:
                circles_arr = np.round(circles[0]).astype(int)
                best_circle = max(circles_arr, key=lambda c: c[2])
                hc_cx, hc_cy, hc_r = best_circle

                avg_diameter_px = float(hc_r * 2)
                main_cx = float(hc_cx) + real_x
                main_cy = float(hc_cy) + real_y

                display_img = self.corrected_image.copy()
                cv2.circle(display_img,
                           (int(main_cx), int(main_cy)), hc_r,
                           (0, 0, 255), 2)
                cross_s = 15
                cv2.line(display_img,
                         (int(main_cx) - cross_s, int(main_cy)),
                         (int(main_cx) + cross_s, int(main_cy)),
                         (0, 0, 255), 2)
                cv2.line(display_img,
                         (int(main_cx), int(main_cy) - cross_s),
                         (int(main_cx), int(main_cy) + cross_s),
                         (0, 0, 255), 2)
                cv2.putText(display_img, "HoughCircles (Fallback)",
                            (50, 50), cv2.FONT_HERSHEY_SIMPLEX,
                            1, (255, 165, 0), 2)

                self.update_image_display(display_img)
                return avg_diameter_px, display_img
            else:
                QMessageBox.warning(
                    self, "Bulunamadı",
                    "Seçtiğiniz alanda dairesel kenar bulunamadı.\n"
                    "(Hem kontur hem HoughCircles denendi.)")
                return None, None

        # ── 8. Sub-pixel hassasiyet (cv2.cornerSubPix) ──
        contour_pts = best_contour.reshape(-1, 1, 2).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS
                    + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)
        try:
            refined_pts = cv2.cornerSubPix(
                filtered, contour_pts, (5, 5), (-1, -1), criteria)
        except cv2.error:
            refined_pts = contour_pts

        # ── 9. Direct Ellipse Fitting ──
        fit_points = refined_pts.reshape(-1, 2)

        if len(fit_points) < 5:
            QMessageBox.warning(self, "Hata",
                                "Yeterli nokta bulunamadı. Farklı alan seçin.")
            return None, None

        try:
            ellipse = cv2.fitEllipseDirect(fit_points)
        except (AttributeError, cv2.error):
            try:
                ellipse = cv2.fitEllipse(fit_points)
            except cv2.error:
                QMessageBox.warning(self, "Hata",
                                    "Elips fit edilemedi. Farklı alan seçin.")
                return None, None

        (center, axes, angle) = ellipse
        major_axis = max(axes[0], axes[1])
        minor_axis = min(axes[0], axes[1])

        # ── 10. Dinamik tolerans ile daire doğrulama ──
        if major_axis == 0:
            QMessageBox.warning(self, "Hata",
                                "Elips eksenleri 0 döndü. Farklı alan seçin.")
            return None, None

        diff_ratio = (major_axis - minor_axis) / major_axis

        # Perspektif düzeltmesi yapılmışsa sıkı, yapılmamışsa gevşek tolerans
        if self.perspective_calibration_done:
            tolerance = 0.02   # %2
        else:
            tolerance = 0.08   # %8

        if diff_ratio > tolerance:
            tol_label = ("Perspektif düzeltilmiş"
                         if self.perspective_calibration_done
                         else "Perspektif düzeltilmemiş")
            QMessageBox.warning(
                self, "Hata",
                f"Seçilen alan çok bozuk.  (Sapma: %{diff_ratio * 100:.1f})\n"
                f"Tolerans: %{tolerance * 100:.0f}  ({tol_label})\n\n"
                f"Daha düz/gölgesiz alan seçin veya perspektif kalibrasyonu yapın.")
            return None, None

        # ── 11. Çap hesabı — sadece major_axis (uzun eksen) ──
        avg_diameter_px = major_axis

        main_cx = center[0] + real_x
        main_cy = center[1] + real_y

        # ── Görsel geribildirim ──
        display_img = self.corrected_image.copy()

        cv2.ellipse(display_img,
                    (int(main_cx), int(main_cy)),
                    (int(axes[0] / 2), int(axes[1] / 2)),
                    angle, 0, 360, (0, 0, 255), 2)

        cross_s = 15
        cv2.line(display_img,
                 (int(main_cx) - cross_s, int(main_cy)),
                 (int(main_cx) + cross_s, int(main_cy)),
                 (0, 0, 255), 2)
        cv2.line(display_img,
                 (int(main_cx), int(main_cy) - cross_s),
                 (int(main_cx), int(main_cy) + cross_s),
                 (0, 0, 255), 2)

        self.update_image_display(display_img)
        return avg_diameter_px, display_img

    # ═══════════════════════════════════════════════════════════════
    #  REFERANS & ÖLÇÜM
    # ═══════════════════════════════════════════════════════════════
    def set_reference(self):
        """Mastar ölçüp referans kalibrasyonu (Piksel/mm) çıkarır."""
        avg_px, _ = self.process_circle_detection()

        if avg_px is not None:
            mm_val, ok = QInputDialog.getDouble(
                self, "Referans Değeri",
                "Mastar parçasının iç çapı kaç milimetre (mm)?",
                20.0, 0.1, 1000.0, 2)
            if ok:
                self.pixel_per_mm = avg_px / mm_val
                self.calibration_done = True
                self.btn_measure.setEnabled(True)

                text = (f"Başarılı!\n"
                        f"Bulunan Çap: {avg_px:.2f} Piksel\n"
                        f"Verilen Çap: {mm_val} mm\n"
                        f"Oran: 1 mm = {self.pixel_per_mm:.2f} Piksel")
                self.lbl_calib_info.setText(text)
                self.status_label.setText("Durum: Referans Alındı.")
                self._save_calibration_data()
                QMessageBox.information(self, "Bilgi", text)
            else:
                self.update_image_display(
                    self.corrected_image.copy(), draw_roi=True)

    def measure_part(self):
        """Piksel/mm oranını kullanarak ölçüm yapar."""
        if not self.calibration_done:
            QMessageBox.warning(self, "Uyarı",
                                "Lütfen önce 'Referans Ölçü' alın.")
            return

        avg_px, display_img = self.process_circle_detection()
        if avg_px is not None and display_img is not None:
            mm_result = avg_px / self.pixel_per_mm

            text = f"TESPIT EDILEN CAP: {mm_result:.2f} mm"
            cv2.putText(display_img, text, (50, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 5)

            self.update_image_display(display_img)
            self.status_label.setText(
                f"Durum: Ölçüm Tamamlandı.  Çap = {mm_result:.2f} mm")
            QMessageBox.information(
                self, "Ölçüm Sonucu",
                f"Parça Çapı: {mm_result:.2f} mm\n"
                f"(Uzun eksen referanslı)")


# ═══════════════════════════════════════════════════════════════════
#  ANA GİRİŞ NOKTASI
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow { background-color: #f0f0f0; }
        QPushButton {
            font-size: 13px; font-weight: bold;
            background-color: #0078D7; color: white;
            border-radius: 5px; padding: 8px;
        }
        QPushButton:hover { background-color: #005A9E; }
        QPushButton:disabled { background-color: #cccccc; color: #666666; }
        QLabel { font-size: 13px; }
        QGroupBox {
            font-size: 13px; font-weight: bold;
            border: 1px solid #999; border-radius: 5px;
            margin-top: 10px; padding-top: 15px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
        }
    """)
    ex = MainApp()
    ex.show()
    sys.exit(app.exec_())
