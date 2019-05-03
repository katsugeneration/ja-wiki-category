# Limitations under the MIT License.
# Copyright 2019 Katsuya Shimabukuro.
"""Generate Wikipedia Category to All Link Page Dictionary.
"""
import pickle
import json
import codecs
import copy
from collections import defaultdict
import gzip
import os
import re
import urllib.request as urllib

re_parentheses = re.compile("\((\d+),\d+,'?([^,']+)'?,[^\)]+\)")
re_categorylinks = re.compile("\((\d+),'?([^,']+)'?,'?([^,']+)'?,'?([^,']+)'?,'?([^,']+)'?,'?([^,']+)'?,'?([^,']+)'?[^\)]+\)")

URL_PAGES = ('https://dumps.wikimedia.org/jawiki/latest/jawiki-latest-page.sql.gz')
URL_CATEGORYLINKS = ('https://dumps.wikimedia.org/jawiki/latest/jawiki-latest-categorylinks.sql.gz')
HIRAGANA = set(map(chr, range(12353, 12353+86)))
KATAKANA = set(map(chr, range(12449, 12449+90)))


def download():
    """Download Wikipedia dump data.
    """
    for url in (URL_PAGES, URL_CATEGORYLINKS):
        print('download: %s' % url)
        if not os.path.exists(os.path.basename(url)):
            urllib.urlretrieve(url, os.path.basename(url))


def extract_id_title(path):
    """Extract id and title to Wikipedia pages dump.

    Args:
        path (String): page dump data path.

    Retunr:
        id2title (Hash[String, String]): page id to page title dictionary.
    """
    with gzip.GzipFile(path) as f:
        id2title = dict(re_parentheses.findall(f.read().decode('utf8')))
    return id2title


def _decode_error_handler(err):
    """Decode function error handler for printing error content.
    """
    print("Decode Error:", str(err.start), '-', str(err.end), err.object[err.start:err.end])
    return ('', err.end)


def extract_categorylinks(id2title, path):
    """Extract category under pages and subcategories to categorylinks dump.

    Args:
        id2title (Hash[String, String]): page id to page title dictionary.
        path (String): categorylinks dump data path.

    Return:
        categorypages (Hash[String, Set[String]]): category to page titles dictionary.
        categorygraph (Hash[String, Set[String]]): category to sub categories dictionary.
    """
    codecs.register_error('original', _decode_error_handler)
    categorypages = defaultdict(set)
    categorygraph = defaultdict(set)
    with gzip.GzipFile(path) as f:
        for (from_id, to, from_name, _, _, _, category_type) in re_categorylinks.findall(f.read().decode('utf8', errors='original')):
            if from_id in id2title:
                _from = id2title[from_id]

                if category_type == 'subcat':
                    if _from == to:
                        continue
                    categorygraph[to].add(_from)
                else:
                    categorypages[to].add(_from)
            else:
                print("Invalid ID:", from_id, from_name)
    return categorypages, categorygraph


def topological_sort_dfs(categorygraph):
    """Return topological sorted list (DFS algorithm in  Cormen's book).

    Args:
        categorygraph (Hash[String, Set[String]]): category to category list dictionary.

    Return:
        L (List[String]): topological sorted list.
    """
    class Node(object):
        def __init__(self):
            self.temporary = False
            self.permanent = False

    L = []
    V = defaultdict(Node)

    def visit(v: str):
        if V[v].permanent:
            return
        if V[v].temporary:
            raise Exception("Graph has at least one cycle")

        V[v].temporary = True
        if v in categorygraph:
            for m in categorygraph[v]:
                visit(m)

        V[v].temporary = False
        V[v].permanent = True
        L.insert(0, v)

    nodes = set()
    for v in categorygraph.values():
        nodes |= set(v)
    nodes |= set(categorygraph.keys())

    while len(nodes) != 0:
        v = nodes.pop()
        visit(v)

    return L


def update_categorylinks_without_scc(categorypages, categorygraph):
    """Update categorypages for containing all reachable content.

    Args:
        categorypages (Hash[String, Set[String]]): category to page name list dictionary.
        categorygraph (Hash[String, Set[String]]): category to category list dictionary.

    Return:
        categorypages (Hash[Int, Set[String]]): updated categorypages for containing all reachable content.
    """
    sorted_list = topological_sort_dfs(categorygraph)

    categories = set()
    for k in categorygraph:
        categories |= categorygraph[k]
    categories |= set(categorygraph.keys())
    categories = list(categories)
    category2indices = {c: i for i, c in enumerate(categories)}

    inversed_categorygraph = defaultdict(set)
    for k, v in categorygraph.items():
        for category in v:
            inversed_categorygraph[category].add(k)

    updated_categorypages = defaultdict(set)
    for node, i in category2indices.items():
        if node in categorypages:
            updated_categorypages[i] |= set(categorypages[node])
    for node in reversed(sorted_list):
        if node in inversed_categorygraph:
            for v in inversed_categorygraph[node]:
                updated_categorypages[v] |= updated_categorypages[node]

    return updated_categorypages, category2indices


def show_category_directlinks(categorypages, categorygraph, category):
    """Print direct link pages and sub categories under the category.

    Args:
        categorypages (Hash[String, Set[String]]): category to page titles dictionary.
        categorygraph (Hash[String, Set[String]]): category to sub categories dictionary.
        category (String): target category name.
    """
    if category in categorygraph:
        print("Sub Categories:", categorygraph[category])
    if category in categorypages:
        print("Pages:", categorypages[category])


def write(obj, path):
    print('write: %s' % path)
    with open(path, 'wb') as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def load(path):
    print('load: %s' % path)
    obj = None
    with open(path, 'rb') as f:
        obj = pickle.load(f)
    return obj


if __name__ == '__main__':
    # download()
    # id2title = extract_id_title(path='jawiki-latest-page.sql.gz')
    # categorypages, categorygraph = extract_categorylinks(id2title, path='jawiki-latest-categorylinks.sql.gz')
    # write(categorypages, path='categorypages.pkl')
    # write(categorygraph, path='categorygraph.pkl')
    categorypages = load(path='categorypages.pkl')
    categorygraph = load(path='categorygraph.pkl')
    update_categorylinks_without_scc(categorypages, categorygraph)