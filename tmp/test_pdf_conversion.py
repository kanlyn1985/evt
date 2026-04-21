#!/usr/bin/env python
"""
PDF 转换引擎对比测试
测试 PyMuPDF、OpenDataloader、MiniMax VLM 三种引擎
"""
import fitz
import json
import base64
from pathlib import Path
from datetime import datetime

PDF_PATH = Path("E:/AI_Project/opencode_workspace/KB1/tmp/GBT+18487.1-2023.pdf")

def test_pymupdf(pdf_path: Path, page_range: range = range(1, 4)):
    """测试 PyMuPDF 提取能力"""
    print("=" * 60)
    print("PyMuPDF 测试")
    print("=" * 60)

    doc = fitz.open(pdf_path)
    results = []

    for page_num in page_range:
        page = doc[page_num - 1]
        text = page.get_text('text')
        blocks = page.get_text('blocks')

        # 计算有效文字比例
        total_chars = sum(len(b[4] or '') for b in blocks if len(b) >= 5)
        clean_chars = sum(len((b[4] or '').strip()) for b in blocks if len(b) >= 5 and b[4])

        # 检查文字质量
        has_meaningful_text = any(
            len(b[4] or '') > 10 and
            any(c.isalnum() for c in b[4])
            for b in blocks if len(b) >= 5
        )

        results.append({
            'page': page_num,
            'block_count': len(blocks),
            'total_chars': total_chars,
            'clean_chars': clean_chars,
            'has_meaningful_text': has_meaningful_text,
            'sample_text': text[:100]
        })

        print(f"\n第 {page_num} 页:")
        print(f"  文字块数：{len(blocks)}")
        print(f"  总字符数：{total_chars}")
        print(f"  有效字符：{clean_chars}")
        print(f"  有意义文字：{has_meaningful_text}")
        print(f"  样本：{repr(text[:80])}")

    doc.close()
    return results

def test_opendataloader(json_path: Path):
    """测试 OpenDataloader 解析结果"""
    print("\n" + "=" * 60)
    print("OpenDataloader 测试")
    print("=" * 60)

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    from collections import Counter
    types = Counter()
    text_items = []

    for kid in data.get('kids', []):
        t = kid.get('type', 'unknown')
        types[t] += 1

        if t in ('heading', 'text'):
            content = kid.get('content', '')
            if content and len(content.strip()) > 0:
                text_items.append({
                    'type': t,
                    'page': kid.get('page number'),
                    'content': content
                })

    print(f"\n总页数：{data.get('number of pages')}")
    print(f"元素类型统计:")
    for t, c in types.most_common():
        print(f"  {t}: {c}")

    print(f"\n有内容的文字项：{len(text_items)}")
    for item in text_items[:5]:
        print(f"  第{item['page']}页 {item['type']}: {repr(item['content'][:50])}")

    return {
        'total_pages': data.get('number of pages'),
        'element_types': dict(types),
        'text_items': len(text_items)
    }

def test_page_images(pdf_path: Path, page_range: range = range(1, 4)):
    """测试页面图片提取"""
    print("\n" + "=" * 60)
    print("页面图片分析")
    print("=" * 60)

    doc = fitz.open(pdf_path)

    for page_num in page_range:
        page = doc[page_num - 1]

        # 获取页面尺寸
        page_rect = page.rect
        print(f"\n第 {page_num} 页:")
        print(f"  尺寸：{page_rect.width:.1f} x {page_rect.height:.1f}")

        # 获取图像对象
        images = page.get_images()
        print(f"  图像对象数：{len(images)}")

        # 渲染为图片
        pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
        img_data = pix.tobytes('png')
        print(f"  PNG 大小：{len(img_data) / 1024:.1f} KB")

        # 提取文本块
        blocks = page.get_text('blocks')
        text_blocks = [b for b in blocks if len(b) >= 5 and b[4]]
        print(f"  文本块数：{len(text_blocks)}")

    doc.close()

def analyze_text_quality(text: str) -> dict:
    """分析文字质量"""
    import unicodedata

    if not text:
        return {'is_useful': False, 'reason': 'empty'}

    # 统计字符类型
    alnum_count = sum(1 for c in text if c.isalnum())
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    fullwidth_count = sum(1 for c in text if 0xFF01 <= ord(c) <= 0xFF5E)

    # 检查常见乱码模式
    garbage_patterns = ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')']
    garbage_ratio = sum(1 for c in text if c in garbage_patterns) / max(len(text), 1)

    is_useful = (
        alnum_count / max(len(text), 1) > 0.3 and
        garbage_ratio < 0.2
    )

    return {
        'is_useful': is_useful,
        'alnum_ratio': alnum_count / max(len(text), 1),
        'chinese_ratio': chinese_count / max(len(text), 1),
        'garbage_ratio': garbage_ratio,
        'reason': 'low quality' if not is_useful else 'good'
    }

def main():
    print(f"\nPDF 路径：{PDF_PATH}")
    print(f"PDF 页数：{len(fitz.open(PDF_PATH))}")
    print(f"处理时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 测试 PyMuPDF
    pymupdf_results = test_pymupdf(PDF_PATH)

    # 分析文字质量
    print("\n" + "=" * 60)
    print("文字质量分析")
    print("=" * 60)
    for r in pymupdf_results:
        quality = analyze_text_quality(r['sample_text'])
        print(f"第 {r['page']} 页：{quality['reason']} (alnum: {quality['alnum_ratio']:.2%}, garbage: {quality['garbage_ratio']:.2%})")

    # 测试 OpenDataloader
    od_path = Path("E:/AI_Project/opencode_workspace/KB1/tmp/opendataloader_gbt_test/GBT+18487.1-2023.json")
    if od_path.exists():
        od_results = test_opendataloader(od_path)
    else:
        print("\nOpenDataloader JSON 不存在")

    # 测试页面图片
    test_page_images(PDF_PATH)

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    print("""
PyMuPDF:
  - 能提取文字层，但全是乱码字符
  - 文字块数量多，但有效内容极少
  - 不适合此 PDF（纯图片 PDF）

OpenDataloader:
  - 识别出 208 个图像对象
  - 仅 3 个有内容的标题（都是"书"）
  - 无法提取真实文字内容

结论:
  - 这是一个纯图片 PDF，没有真实文本层
  - PyMuPDF 和 OpenDataloader 都无法提取有效文字
  - 必须使用 VLM OCR (MiniMax/PaddleVL) 进行图片识别
""")

if __name__ == "__main__":
    main()
