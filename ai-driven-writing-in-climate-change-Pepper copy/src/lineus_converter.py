#!/usr/bin/env python3
"""
LineUs专用线稿转G代码
使用LineUs特定的坐标系统和G代码格式
"""

import numpy as np
import cv2
import sys


class LineUsConverter:
    def __init__(self, quality='high', use_full_area=True):
        """
        初始化LineUs转换器
        
        Args:
            quality: 'low'(快速), 'medium'(平衡), 'high'(高质量), 'ultra'(极高)
            use_full_area: True=使用最大区域, False=使用安全区域
        """
        # LineUs坐标系统 (机器单位)
        # 原点在伺服轴中心，home点是(1000, 1000)
        # 主绘图区域: X: 650-1775, Y: -1000-1000
        # 100单位 ≈ 5mm
        
        if use_full_area:
            # 使用最大安全绘图区域
            self.X_MIN = 650
            self.X_MAX = 1775
            self.Y_MIN = -1000
            self.Y_MAX = 1000
        else:
            # 保守安全区域
            self.X_MIN = 700
            self.X_MAX = 1700
            self.Y_MIN = -900
            self.Y_MAX = 900
        
        self.Z_DOWN = 0      # 笔下
        self.Z_UP = 1000     # 笔上
        
        # 计算绘图区域尺寸
        self.drawing_width = self.X_MAX - self.X_MIN
        self.drawing_height = self.Y_MAX - self.Y_MIN
        
        # 质量设置
        self.quality_settings = {
            'low': {'epsilon': 3.0, 'blur': 0, 'morph': 1, 'min_area': 20},
            'medium': {'epsilon': 2.0, 'blur': 0, 'morph': 1, 'min_area': 10},
            'high': {'epsilon': 1.0, 'blur': 3, 'morph': 2, 'min_area': 5},
            'ultra': {'epsilon': 0.5, 'blur': 5, 'morph': 2, 'min_area': 3}
        }
        
        self.quality = quality
        self.settings = self.quality_settings[quality]
        
        print(f"质量模式: {quality.upper()}")
        print(f"绘图区域: {self.drawing_width}单位 × {self.drawing_height}单位")
        print(f"         ≈ {self.drawing_width/20:.1f}mm × {self.drawing_height/20:.1f}mm")
        
    def load_image(self, image_path):
        """加载并高质量处理图像"""
        img = cv2.imread(image_path, 0)
        if img is None:
            raise ValueError(f"无法读取: {image_path}")
        
        print(f"原始图像: {img.shape[1]}×{img.shape[0]}px")
        
        # 高质量预处理
        if self.settings['blur'] > 0:
            # 高斯模糊去噪
            img = cv2.GaussianBlur(img, (self.settings['blur'], self.settings['blur']), 0)
        
        # 自适应二值化（比固定阈值更好）
        binary = cv2.adaptiveThreshold(
            img, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 
            11, 2
        )
        
        # 形态学处理
        if self.settings['morph'] > 0:
            kernel = np.ones((self.settings['morph'], self.settings['morph']), np.uint8)
            # 闭运算：连接断裂的线条
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            # 开运算：去除小噪点
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        
        return binary, img.shape
    
    def extract_contours(self, binary_img):
        """提取并简化轮廓（使用质量设置）"""
        contours, _ = cv2.findContours(binary_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        simplified = []
        epsilon = self.settings['epsilon']
        min_area = self.settings['min_area']
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            
            # 使用质量设置的epsilon值简化
            approx = cv2.approxPolyDP(contour, epsilon, True)
            points = approx.squeeze()
            
            if len(points.shape) == 1:
                points = points.reshape(-1, 2)
            
            if len(points) >= 3:
                simplified.append(points)
        
        return simplified
    
    def optimize_order(self, contours):
        """优化绘制顺序"""
        if not contours:
            return []
        
        optimized = []
        remaining = list(range(len(contours)))
        current_pos = np.array([self.X_MIN + self.drawing_width//2, 0])
        
        while remaining:
            min_dist = float('inf')
            best_idx = 0
            best_reverse = False
            
            for i, idx in enumerate(remaining):
                path = contours[idx]
                
                dist_start = np.linalg.norm(path[0] - current_pos)
                dist_end = np.linalg.norm(path[-1] - current_pos)
                
                if dist_start < min_dist:
                    min_dist = dist_start
                    best_idx = i
                    best_reverse = False
                
                if dist_end < min_dist:
                    min_dist = dist_end
                    best_idx = i
                    best_reverse = True
            
            idx = remaining.pop(best_idx)
            path = contours[idx]
            
            if best_reverse:
                path = path[::-1]
            
            optimized.append(path)
            current_pos = path[-1]
        
        return optimized
    
    def image_to_lineus_coords(self, contours, img_shape):
        """将图像坐标转换为LineUs机器坐标"""
        img_height, img_width = img_shape
        
        converted = []
        for contour in contours:
            # 计算缩放比例（保持纵横比）
            scale_x = self.drawing_width / img_width
            scale_y = self.drawing_height / img_height
            scale = min(scale_x, scale_y)
            
            # 计算居中偏移
            scaled_width = img_width * scale
            scaled_height = img_height * scale
            offset_x = self.X_MIN + (self.drawing_width - scaled_width) / 2
            offset_y = (self.drawing_height - scaled_height) / 2
            
            # 转换坐标
            new_contour = []
            for point in contour:
                x = point[0] * scale + offset_x
                y = (img_height - point[1]) * scale + offset_y - 1000  # Y轴翻转并调整到LineUs坐标系
                new_contour.append([int(x), int(y)])
            
            converted.append(np.array(new_contour))
        
        return converted
    
    def generate_lineus_gcode(self, contours, output_path):
        """生成LineUs专用G代码"""
        gcode = []
        
        # 头部注释
        gcode.append("; LineUs Drawing GCode")
        gcode.append(f"; Total paths: {len(contours)}")
        gcode.append("")
        
        # 抬笔并移动到起始区域
        gcode.append(f"G01 X{1000} Y{0} Z{self.Z_UP}")
        gcode.append("")
        
        # 绘制每条路径
        for i, contour in enumerate(contours):
            gcode.append(f"; Path {i+1}/{len(contours)}")
            
            # 移动到起点（笔抬起）
            x0, y0 = contour[0]
            gcode.append(f"G01 X{x0} Y{y0} Z{self.Z_UP}")
            
            # 下笔
            gcode.append(f"G01 X{x0} Y{y0} Z{self.Z_DOWN}")
            
            # 绘制路径的每个点
            for point in contour[1:]:
                x, y = point
                gcode.append(f"G01 X{x} Y{y} Z{self.Z_DOWN}")
            
            # 闭合路径
            gcode.append(f"G01 X{x0} Y{y0} Z{self.Z_DOWN}")
            
            # 抬笔
            gcode.append(f"G01 X{x0} Y{y0} Z{self.Z_UP}")
            gcode.append("")
        
        # 返回home位置
        gcode.append("; Return to home")
        gcode.append(f"G01 X{1000} Y{0} Z{self.Z_UP}")
        
        # 保存
        with open(output_path, 'w') as f:
            f.write('\n'.join(gcode))
        
        print(f"✓ LineUs G代码: {output_path}")
        print(f"  路径数: {len(contours)}")
        print(f"  坐标范围: X({self.X_MIN}-{self.X_MAX}) Y({self.Y_MIN}-{self.Y_MAX})")
        
        return len(gcode)
    
    def process(self, input_image, output_gcode):
        """完整处理流程"""
        print("=" * 50)
        print("LineUs专用转换 - 高质量模式")
        print("=" * 50)
        
        # 加载图像
        print("\n[1/5] 加载图像...")
        binary, img_shape = self.load_image(input_image)
        
        # 提取轮廓
        print("\n[2/5] 提取轮廓...")
        contours = self.extract_contours(binary)
        print(f"轮廓数: {len(contours)}")
        
        # 优化顺序
        print("\n[3/5] 优化顺序...")
        contours = self.optimize_order(contours)
        
        # 转换坐标
        print("\n[4/5] 转换为LineUs坐标...")
        contours = self.image_to_lineus_coords(contours, img_shape)
        
        # 统计点数
        total_points = sum(len(c) for c in contours)
        print(f"总点数: {total_points}")
        
        # 生成G代码
        print("\n[5/5] 生成G代码...")
        lines = self.generate_lineus_gcode(contours, output_gcode)
        
        print("\n" + "=" * 50)
        print(f"完成! 共{lines}行G代码")
        print("=" * 50)
        print("\n发送到LineUs的方法:")
        print("python send_to_lineus.py", output_gcode)


def main():
    if len(sys.argv) < 2:
        print("用法: python lineus_converter.py <图像文件> [质量]")
        print("质量选项: low, medium, high, ultra")
        print("\n使用测试图像（ultra质量）...")
        input_file = "/home/claude/test_lineart.png"
        quality = 'ultra'
    else:
        input_file = sys.argv[1]
        quality = sys.argv[2] if len(sys.argv) > 2 else 'high'
    
    output_file = "/mnt/user-data/outputs/lineus_output.gcode"
    
    converter = LineUsConverter(quality=quality, use_full_area=True)
    converter.process(input_file, output_file)


if __name__ == "__main__":
    main()
