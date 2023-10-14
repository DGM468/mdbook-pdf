import argparse
import fitz
import json
import os
import re
import requests
import lxml.etree
import argparse
import sys


def get_titles():
    try:
        html = requests.get(url).text
    except e:
        print("网络异常")
    html_tree = lxml.etree.HTML(html, parser=None)
    elements = html_tree.cssselect('li > a')
    titles = []
    for e in elements:
        s = e.cssselect('strong')
        href = e.get("href").replace('.html', '')
        # 一般：有标题序号的（8.4.2）
        if s:
            s = s[0]
            count = 0   # 根据标题序号 . 确定标题层级
            count = s.text.count('.')
            if count == 1:
                titles.append(f'1, {s.text}{s.tail}, {href}')
            elif count == 2:
                titles.append(f'  2, {s.text}{s.tail}, {href}')
            elif count == 3:
                titles.append(f'    3, {s.text}{s.tail}, {href}')
            else:
                print('异常：无法确定标题层级')
        # 特殊：没有标题序号的
        else:
            titles.append(f'1, {e.text}, {href}')
    return titles


def get_page_numbers(pdf_path):
    numbers = []
    pdf_document = fitz.open(pdf_path)
    for page in pdf_document:
        mark = False    # 标记是否在一个页面，mdbook中 一般一个标题只在一个页面
        dict = page.get_text("dict")
        blocks = dict["blocks"]
        title = ''
        for block in blocks:
            if "lines" in block.keys():
                spans = block['lines']
                for span in spans:
                    data = span['spans']
                    for lines in data:
                        # lines['text'] -> string, lines['size'] -> font size, lines['font'] -> font name
                        if lines['size'] == 24.0:
                            mark = True
                            title = lines['text']

        if mark:
            numbers.append((page.number, title))
    pdf_document.close()
    return numbers


def combine(titles, numbers, maps):
    for (number, title) in zip(numbers, titles):
        s = title.split(',')[2]
        if s.strip() in maps:   # 已有的不加
            print('已有的：')
            print(s.strip(), maps[s.strip()])
        else:
            maps[s.strip()] = {'number': number[0], 'react': [47.0, 36.0]}
    return maps


def get_maps_by_pdf(pdf_path):
    pdf_document = fitz.open(pdf_path)
    # 获取书签列表
    maps = {}
    # count = 0
    for page in pdf_document.pages():
        for linkdict in page.links():
            if linkdict['uri'].startswith(title_url):
                # 保留 print.html#
                name = linkdict['uri'].replace(url, '')
                if name == '':   # 无标题
                    continue
                if name in maps and maps[name]['number'] != page.number:    # 已有的检查
                    print(f'注意 {name}')
                (a, b, _, _) = linkdict['from']
                name = name.replace('.html', '')
                maps[name] = {'number': page.number, 'react': (a, b)}
                # count += 1
    pdf_document.close()
    return maps


def modify_links(page, linkdict, maps):
    jing = re.compile(r'#.+')
    xiegang = re.compile(r'[a-z-_/]+\.html')
    # 1. 标题的 url 直接删除
    if linkdict['uri'].startswith(title_url):
        page.delete_link(linkdict)
        return
    # 2. 不是书的主页开头的 url 跳过
    if not linkdict['uri'].startswith(url):
        return
    # 3. 转换
    # print(linkdict['uri'])
    suffix_url = linkdict['uri'].replace(url, '')
    res = ''    # 根据 url 获取 key
    # 跳转网址带斜杠 ----> 跳书签
    mat = xiegang.search(suffix_url)
    if mat:
        res = mat[0].replace('.html', '')
    # 跳转网址带'#' ----> 跳pdf
    mat = jing.search(suffix_url)
    if mat:
        res = 'print' + mat[0]
    if res != '' and res not in maps:   # 检查有没有没处理的跳转
        print('没处理:'+linkdict['uri']+' '+str(page.number + 1))
    if res in maps:
        page.delete_link(linkdict)
        page_num = maps[res]['number']
        (a, b) = maps[res]['react']
        # new_linkdict = {
        # 'kind': 4, 'xref': linkdict['xref'], 'from': linkdict['from'], 'name': f'page={page_num}&view=Fit', 'id': ''}
        new_linkdict = {
            "kind": fitz.LINK_GOTO, "page": page_num, "from": linkdict['from'], "to": fitz.Point(a, b)}
        page.insert_link(new_linkdict)


def uri_to_dest(pdf_path, maps, out_name):
    pdf_document = fitz.open(pdf_path)
    for page in pdf_document.pages():
        for linkdict in page.links():
            modify_links(page, linkdict, maps)
    pdf_document.save(out_name)
    pdf_document.close()


def get_toc(toc_json):
    toc = json.load(open(toc_json))
    numbers = toc['numbers']
    bookmarks = toc['titles']
    toc = []
    for (a, b) in zip(numbers, bookmarks):
        s = b.split(',')
        level = int(s[0])
        title = s[1]
        number = a[0]
        toc.append([level, title, number + 1])
    return toc


def add_bookmarks(pdf_path):
    toc = get_toc(toc_json)
    pdf_document = fitz.open(pdf_path)
    pdf_document.set_toc(toc)
    pdf_document.save(f'{book_name}_bookmarks.pdf')


def print_links(pdf_path):
    pdf_document = fitz.open(pdf_path)
    for page in pdf_document.pages():
        for linkdict in page.links():
            # if 'uri' in linkdict:
            print(linkdict)


def save_maps(pdf_path):
    # 先获取书签的 maps，可能需要手动修正
    if not os.path.exists(toc_json):
        numbers = get_page_numbers(pdf_path)
        titles = get_titles()
        bookmarks = {
            'numbers': numbers,
            'titles': titles
        }
        if len(numbers) != len(titles):
            print(
                f'页码个数：{len(numbers)} 书签个数：{len(titles)}，请手动修正 toc_json， 修正之后再运行此脚本')
        json.dump(bookmarks, open(toc_json, 'w'), indent=4)
        sys.exit()
    toc = json.load(open(toc_json, 'r'))
    l1 = len(toc['numbers'])
    l2 = len(toc['titles'])
    if l1 != l2:
        print(f"页码个数：{l1} 标题个数：{l2}，请手动修正 toc_json， 修正之后在运行此脚本")
        sys.exit()
    else:
        print(f'页码个数：{l1} 标题个数：{l2} 验证通过')

    if not os.path.exists(maps_json):
        maps = get_maps_by_pdf(pdf_path)
        toc = json.load(open(toc_json))
        maps = combine(toc['titles'], toc['numbers'], maps)
        json.dump(maps, open(maps_json, 'w'), indent=4)


def clean():
    if os.path.exists(toc_json):
        os.remove(toc_json)
    if os.path.exists(maps_json):
        os.remove(maps_json)
    if os.path.exists(f'{book_name}_mod.pdf'):
        os.remove(f'{book_name}_mod.pdf')

def main(pdf_path):
    # todo
    # print pdf
    
    # 获取 maps
    save_maps(pdf_path)
    # 替换(超链接 -> pdf内跳转)
    uri_to_dest(pdf_path, json.load(open(maps_json)), f'{book_name}_mod.pdf')
    # 添加书签
    add_bookmarks(f'{book_name}_mod.pdf')

    clean()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--url', help='URL')
    parser.add_argument('-p', '--path', help='PDF path')
    args = parser.parse_args()

    url = args.url or ''
    pdf_path = args.path or ''

    print(f'url: {url}\npdf_path: {pdf_path}')
    # mdbook 标题
    title_url = f'{url}print.html#'
    book_name =re.compile('[^/]+\.pdf$').match(pdf_path)[0].replace('.pdf', '')
    toc_json = f'{book_name}_toc.json'
    maps_json = f'{book_name}_maps.json'

    main(pdf_path)



