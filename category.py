# Limitations under the MIT License.
# Copyright 2019 Katsuya Shimabukuro.
"""Generate Wikipedia Category to All Link Page Dictionary.
"""
import pickle
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


def extract_categorylinks(id2title, path):
    """Extract category under pages and subcategories to categorylinks dump.

    Args:
        id2title (Hash[String, String]): page id to page title dictionary.
        path (String): categorylinks dump data path.

    Return:
        categorypages (Hash[String, Set[String]]): category to page titles dictionary.
        categorygraph (Hash[String, Set[String]]): category to sub categories dictionary.
    """
    categorypages = defaultdict(set)
    categorygraph = defaultdict(set)
    with gzip.GzipFile(path) as f:
        for (from_id, to, from_name, _, _, _, category_type) in re_categorylinks.findall(f.read().decode('utf8', errors='ignore')):
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
        categorygraph (Hash[T, Set[T]]): category to category list dictionary.

    Return:
        L (List[T]): topological sorted list.
    """
    class Node(object):
        def __init__(self):
            self.temporary = False
            self.permanent = False

    L = []
    V = defaultdict(Node)

    def visit(v):
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


def decompose_scc(categorygraph):
    """Return strongly connected components (Tarjan's algorithm).

    Args:
        categorygraph (Hash[T, Set[T]]): category to category list dictionary.

    Return:
        L (List[Set[T]]): strongly connected components list.
    """
    class Node(object):
        def __init__(self):
            self.index = None
            self.lowlink = None
            self.onStack = False

    i = 0
    L = []
    S = []
    V = defaultdict(Node)

    def strong_connect(v):
        nonlocal i
        nonlocal V
        nonlocal S
        nonlocal L

        V[v].index = i
        V[v].lowlink = i
        i += 1
        S.append(v)
        V[v].onStack = True

        if v in categorygraph:
            for w in categorygraph[v]:
                if V[w].index is None:
                    strong_connect(w)
                    V[v].lowlink = min(V[v].lowlink, V[w].lowlink)
                elif V[w].onStack:
                    V[v].lowlink = min(V[v].lowlink, V[w].index)

        if V[v].lowlink == V[v].index:
            new_c = set()
            w = S.pop()
            V[w].onStack = False
            new_c.add(w)
            while v != w:
                w = S.pop()
                V[w].onStack = False
                new_c.add(w)
            L.append(new_c)

    nodes = set()
    for v in categorygraph.values():
        nodes |= set(v)
    nodes |= set(categorygraph.keys())

    for v in nodes:
        if V[v].index is None:
            strong_connect(v)

    return L


def _update_categorygraph(categorypages, categorygraph, category2indices):
    """Update categorygraph for containing all reachable content.

    Args:
        categorypages (Hash[String, Set[String]]): category to page name list dictionary.
        categorygraph (Hash[String, Set[String]]): category to category list dictionary.
        category2indices (Hash[String, Int]): category to category index list dictionary.

    Return:
        categorygraph (Hash[Int, Set[Int]]): updated categorygraph for containing all reachable content.
        categorypages (Hash[Int, Set[String]]): category index to page name list dictionary.
    """
    updated_categorygraph = defaultdict(set)
    inversed_categorygraph = defaultdict(set)

    for c in categorygraph:
        for v in categorygraph[c]:
            updated_categorygraph[category2indices[c]].add(category2indices[v])
            inversed_categorygraph[category2indices[v]].add(category2indices[c])
        # Remove self loop
        updated_categorygraph[category2indices[c]] -= set([category2indices[c]])
        inversed_categorygraph[category2indices[c]] -= set([category2indices[c]])
    sorted_list = topological_sort_dfs(updated_categorygraph)

    for n in reversed(sorted_list):
        if n in inversed_categorygraph:
            for v in inversed_categorygraph[n]:
                updated_categorygraph[v] |= updated_categorygraph[n]

    updated_categorypages = defaultdict(set)
    for node, i in category2indices.items():
        if node in categorypages:
            updated_categorypages[i] |= set(categorypages[node])

    return updated_categorygraph, updated_categorypages


def update_categorygraph_without_scc(categorypages, categorygraph):
    """Update categorygraph for containing all reachable content without scc.

    Args:
        categorypages (Hash[String, Set[String]]): category to page name list dictionary.
        categorygraph (Hash[String, Set[String]]): category to category list dictionary.

    Return:
        categorypages (Hash[Int, Set[Int]]): updated categorygraph for containing all reachable content.
        categorypages (Hash[Int, Set[String]]): category index to page name list dictionary.
        category2indices (Hash[String, Int]): category to category index list dictionary.
    """

    categories = set()
    for k in categorygraph:
        categories |= categorygraph[k]
    categories |= set(categorygraph.keys())
    categories = list(categories)
    category2indices = {c: i for i, c in enumerate(categories)}

    updated_categorygraph, updated_categorypages = _update_categorygraph(categorypages, categorygraph, category2indices)
    return updated_categorygraph, updated_categorypages, category2indices


def update_categorygraph(categorypages, categorygraph):
    """Update categorygraph for containing all reachable content.

    Args:
        categorypages (Hash[String, Set[String]]): category to page name list dictionary.
        categorygraph (Hash[String, Set[String]]): category to category list dictionary.

    Return:
        categorygraph (Hash[Int, Set[Int]]): updated categorygraph for containing all reachable content.
        categorypages (Hash[Int, Set[String]]): category index to page name list dictionary.
        category2indices (Hash[String, Int]): category to category index list dictionary.
    """
    scc_list = decompose_scc(categorygraph)
    category2indices = {c: i for i, scc in enumerate(scc_list) for c in scc}

    updated_categorygraph, updated_categorypages = _update_categorygraph(categorypages, categorygraph, category2indices)
    return updated_categorygraph, updated_categorypages, category2indices


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


def show_category_alllinks_with_dfs(categorypages, categorygraph, category):
    """Print all link pages and sub categories under the category.

    Args:
        categorypages (Hash[String, Set[String]]): category to page titles dictionary.
        categorygraph (Hash[String, Set[String]]): category to sub categories dictionary.
        category (String): target category name.
    """
    class Node(object):
        def __init__(self):
            self.visited = False

    V = defaultdict(Node)
    categories = set()
    pages = set()

    def visit(v):
        nonlocal pages
        nonlocal categories

        if V[v].visited:
            return
        V[v].visited = True
        if v in categorypages:
            pages |= categorypages[v]
        if v in categorygraph:
            categories |= categorygraph[v]
            for m in categorygraph[v]:
                visit(m)

    visit(category)
    print("Sub Categories:", categories)
    print("Pages:", pages)


def show_category_alllinks(categorypages, categorygraph, category2indices, category):
    """Print all link pages and sub categories under the category.

    Args:
        categorypages (Hash[Int, Set[String]]): category index to page titles dictionary.
        categorygraph (Hash[Int, Set[Int]]): category index to sub categories dictionary.
        category2indices (Hash[String, Int]): category to category index list dictionary.
        category (String): target category name.
    """
    index2categories = defaultdict(set)
    for c, i in category2indices.items():
        index2categories[i].add(c)

    if category in category2indices:
        index = category2indices[category]
        categories = []
        pages = [categorypages[index]]
        for sub_c in categorygraph[index]:
            categories.append(sub_c)
            pages.append(categorypages[sub_c])
        categories = set().union(*[index2categories[i] for i in categories])
        pages = set().union(*pages)
        print("Sub Categories:", categories)
        print("Pages:", pages)


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
    download()
    id2title = extract_id_title(path='jawiki-latest-page.sql.gz')
    categorypages, categorygraph = extract_categorylinks(id2title, path='jawiki-latest-categorylinks.sql.gz')
    write(categorypages, path='categorypages.pkl')
    write(categorygraph, path='categorygraph.pkl')
    categorygraph, categorypages, category2indices = update_categorygraph(categorypages, categorygraph)
    write(categorygraph, path='categorygraph_all.pkl')
    write(categorypages, path='categorypages_all.pkl')
    write(category2indices, path='category2indices.pkl')
