# Copyright 2023 The Pigweed Authors
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
"""Generates content related to Pigweed module metadata on pigweed.dev.

This file implements the following pigweed.dev features:

* The `.. pigweed-module::` and `.. pigweed-module-subpage::` directives.
* The auto-generated "Source code" and "Issues" URLs that appear in the site
  nav for each module.

Everything is implemented through the Sphinx Extension API.
"""

from dataclasses import dataclass
import sys
from typing import cast, Dict, List, Optional, TypeVar, Union

# We use BeautifulSoup for certain docs rendering features. It may not be
# available in downstream projects. If so, no problem. We fall back to simpler
# docs rendering.
# pylint: disable=import-error
try:
    from bs4 import BeautifulSoup  # type: ignore
    from bs4.element import Tag as HTMLTag  # type: ignore

    bs_enabled = True
except ModuleNotFoundError:
    bs_enabled = False
# pylint: enable=import-error

import docutils
from docutils import nodes
from docutils.nodes import Element
import docutils.statemachine

# pylint: disable=consider-using-from-import
import docutils.parsers.rst.directives as directives  # type: ignore

# pylint: enable=consider-using-from-import
from sphinx.addnodes import document as Document
from sphinx.application import Sphinx
from sphinx.environment import BuildEnvironment
from sphinx.util.docutils import SphinxDirective

from sphinx_design.cards import CardDirective

EnvAttrT = TypeVar('EnvAttrT')


@dataclass
class ParsedBody:
    topnav: str
    body_without_topnav: str


class EnvMetadata:
    """Easier access to the Sphinx `env` for custom metadata.

    You can store things in the Sphinx `env`, which is just a dict. But each
    time you do, you have to handle the possibility that the key you want
    hasn't been set yet, and set it to a default. The `env` is also untyped,
    so you have to cast the value you get to whatever type you expect it to be.

    Or you can use this class to define your metadata keys up front, and just
    access them like: `value = EnvMetadata(env).my_value`

    ... which will handle initializing the value if it hasn't been yet and
    provide you a typed result.
    """

    def __init__(self, env: BuildEnvironment):
        self._env = env

    def _get_env_attr(self, attr: str, default: EnvAttrT) -> EnvAttrT:
        if not hasattr(self._env, attr):
            value: EnvAttrT = default
            setattr(self._env, attr, value)
        else:
            value = getattr(self._env, attr)

        return value

    @property
    def pw_parsed_bodies(self) -> Dict[str, ParsedBody]:
        default: Dict[str, ParsedBody] = {}
        return self._get_env_attr('pw_module_nav', default)


def status_choice(arg):
    return directives.choice(arg, ('experimental', 'unstable', 'stable'))


def status_badge(module_status: str) -> str:
    """Given a module status, return the status badge for rendering."""
    role = ':bdg-primary:'
    return role + f'`{module_status.title()}`'


def cs_url(module_name: str) -> str:
    """Return the codesearch URL for the given module."""
    return f'https://cs.opensource.google/pigweed/pigweed/+/main:{module_name}/'


def issues_url(module_name: str) -> str:
    """Returns open issues that mention the given module name."""
    return f'https://issues.pigweed.dev/issues?q={module_name}%20status:open'


def concat_tags(*tag_lists: List[str]) -> List[str]:
    """Given a list of tag lists, return them concat'ed and ready for render."""

    all_tags = tag_lists[0]

    for tag_list in tag_lists[1:]:
        if len(tag_list) > 0:
            all_tags.append(':octicon:`dot-fill`')
            all_tags.extend(tag_list)

    return all_tags


def create_topnav(
    subtitle: str,
    extra_classes: Optional[List[str]] = None,
) -> nodes.Node:
    """Create the nodes for the top title and navigation bar."""

    topnav_classes = (
        ['pw-topnav'] + extra_classes if extra_classes is not None else []
    )

    topnav_container = nodes.container(classes=topnav_classes)

    subtitle_node = nodes.paragraph(
        classes=['pw-topnav-subtitle'],
        text=subtitle,
    )

    topnav_container += subtitle_node
    return topnav_container


class PigweedModuleDirective(SphinxDirective):
    """Directive registering module metadata, rendering title & info card."""

    required_arguments = 0
    final_argument_whitespace = True
    has_content = True
    option_spec = {
        'name': directives.unchanged_required,
        'tagline': directives.unchanged_required,
        'status': status_choice,
        'is-deprecated': directives.flag,
        'languages': directives.unchanged,
        'code-size-impact': directives.unchanged,
        'facade': directives.unchanged,
        'nav': directives.unchanged_required,
    }

    def _try_get_option(self, option: str):
        """Try to get an option by name and raise on failure."""

        try:
            return self.options[option]
        except KeyError:
            raise self.error(f' :{option}: option is required')

    def _maybe_get_option(self, option: str):
        """Try to get an option by name and return None on failure."""
        return self.options.get(option, None)

    def run(self) -> List[nodes.Node]:
        module_name = self._try_get_option('name')
        tagline = self._try_get_option('tagline')

        status_tags: List[str] = [
            status_badge(self._try_get_option('status')),
        ]

        if 'is-deprecated' in self.options:
            status_tags.append(':bdg-danger:`Deprecated`')

        language_tags = []

        if 'languages' in self.options:
            languages = self.options['languages'].split(',')

            if len(languages) > 0:
                for language in languages:
                    language = language.strip()
                    if language == 'Rust':
                        language_tags.append(
                            f':bdg-link-info:`{language}'
                            + f'</rustdoc/{module_name}>`'
                        )
                    else:
                        language_tags.append(f':bdg-info:`{language}`')

        code_size_impact = []

        if code_size_text := self._maybe_get_option('code-size-impact'):
            code_size_impact.append(f'**Code Size Impact:** {code_size_text}')

        # Move the directive content into a section that we can render wherever
        # we want.
        raw_content = cast(List[str], self.content)  # type: ignore
        content = nodes.paragraph()
        self.state.nested_parse(raw_content, 0, content)

        # The card inherits its content from this node's content, which we've
        # already pulled out. So we can replace this node's content with the
        # content we need in the card.
        self.content = docutils.statemachine.StringList(
            concat_tags(status_tags, language_tags, code_size_impact)
        )

        card = CardDirective.create_card(
            inst=self,
            arguments=[],
            options={},
        )

        topbar = create_topnav(
            tagline,
            ['pw-module-index'],
        )

        return [topbar, card, content]


class PigweedModuleSubpageDirective(PigweedModuleDirective):
    """Directive registering module metadata, rendering title & info card."""

    required_arguments = 0
    final_argument_whitespace = True
    has_content = True
    option_spec = {
        'name': directives.unchanged_required,
        'tagline': directives.unchanged_required,
        'nav': directives.unchanged_required,
    }

    def run(self) -> List[nodes.Node]:
        tagline = self._try_get_option('tagline')

        topbar = create_topnav(
            tagline,
            ['pw-module-subpage'],
        )

        return [topbar]


def _parse_body(body: str) -> ParsedBody:
    """From the `body` HTML, return the topnav and the body without topnav.

    The fundamental idea is this: Our Sphinx directives can only render nodes
    *within* the docutils doc, but we want to elevate the top navbar *outside*
    of that doc into the web theme. Sphinx by itself provides no mechanism for
    this, since it's model looks something like this:

      ┌──────────────────┐
      │ Theme            │
      │  ┌──────────────┐│    When Sphinx builds HTML, the output is plain HTML
      │  │ Sphinx HTML  ││    with a structure defined by docutils. Themes can
      │  │              ││    build *around* that and cascade styles down *into*
      │  │              ││    that HTML, but there's no mechanism in the Sphinx
      │  └──────────────┘│    build to render docutils nodes in the theme.
      └──────────────────┘

    The escape hatch is this:
    - Render things within the Sphinx HTML output (`body`)
    - Use Sphinx theme templates to run code during the final render phase
    - Extract the HTML from the `body` and insert it in the theme via templates

    So this function extracts the things that we rendered in the `body` but
    actually want in the theme (the top navbar), returns them for rendering in
    the template, and returns the `body` with those things removed.
    """
    if not bs_enabled:
        return ParsedBody('', body)

    def _add_class_to_tag(tag: HTMLTag, classname: str) -> None:
        tag['class'] = tag.get('class', []) + [classname]  # type: ignore

    def _add_classes_to_tag(
        tag: HTMLTag, classnames: Union[str, List[str], None]
    ) -> None:
        tag['class'] = tag.get('class', []) + classnames  # type: ignore

    html = BeautifulSoup(body, features='html.parser')

    # Render the doc unchanged, unless it has the module doc topnav
    if (topnav := html.find('div', attrs={'class': 'pw-topnav'})) is None:
        return ParsedBody('', body)

    assert isinstance(topnav, HTMLTag)

    # Find the topnav title and subtitle
    topnav_title = topnav.find('p', attrs={'class': 'pw-topnav-title'})
    topnav_subtitle = topnav.find('p', attrs={'class': 'pw-topnav-subtitle'})
    assert isinstance(topnav_title, HTMLTag)
    assert isinstance(topnav_subtitle, HTMLTag)

    # Find the single `h1` element, the doc's canonical title
    doc_title = html.find('h1')
    assert isinstance(doc_title, HTMLTag)

    topnav_str = ''

    if 'pw-module-index' in topnav['class']:
        # Take the standard Sphinx/docutils title and add topnav styling
        _add_class_to_tag(doc_title, 'pw-topnav-title')
        # Replace the placeholder title in the topnav with the "official" `h1`
        topnav_title.replace_with(doc_title)
        # Promote the subtitle to `h2`
        topnav_subtitle.name = 'h2'
        # We're done mutating topnav; write it to string for rendering elsewhere
        topnav_str = str(topnav)
        # Destroy the instance that was rendered in the document
        topnav.decompose()

    elif 'pw-module-subpage' in topnav['class']:
        # Take the title from the topnav (the module name), promote it to `h1`
        topnav_title.name = 'h1'
        # Add the heading link, but pointed to the module index page
        heading_link = html.new_tag(
            'a',
            attrs={
                'class': ['headerlink'],
                'href': 'docs.html',
                'title': 'Permalink to module index',
            },
        )
        heading_link.string = '#'
        topnav_title.append(heading_link)
        # Promote the subtitle to `h2`
        topnav_subtitle.name = 'h2'
        # We're done mutating topnav; write it to string for rendering elsewhere
        topnav_str = str(topnav)
        # Destroy the instance that was rendered in the document
        topnav.decompose()

    return ParsedBody(topnav_str, str(html))


def setup_parse_body(_app, _pagename, _templatename, context, _doctree):
    def parse_body(body: str) -> ParsedBody:
        return _parse_body(body)

    context['parse_body'] = parse_body


def fix_canonical_url(canonical_url: Optional[str]) -> Optional[str]:
    """Rewrites the canonical URL for `pigweed.dev/*/docs.html` pages.

    Our server is configured to remove `docs.html` from URLs. E.g.
    pigweed.dev/pw_string/docs.html` redirects to `pigweed.dev/pw_string`.
    To improve our SEO, the `<link rel="canonical" href="..."/>` tag in our
    HTML should match the URL that the server provides.

    Args:
        docname:
            Basically the relative path to the doc, except `.rst` is omitted
            from the filename. E.g. `pw_string/docs`.
        canonical_url:
            The default canonical URL that Sphinx has generated for the doc.

    Returns:
        The corrected canonical URL if the page would normally end with
        `docs.html`, otherwise the original canonical URL value unmodified.
    """
    if canonical_url is None or not canonical_url.endswith('/docs.html'):
        return canonical_url
    canonical_url = canonical_url.replace('/docs.html', '/')
    return canonical_url


def on_html_page_context(
    app: Sphinx,  # pylint: disable=unused-argument
    docname: str,  # pylint: disable=unused-argument
    templatename: str,  # pylint: disable=unused-argument
    context: Optional[Dict[str, Optional[str]]],
    doctree: Document,  # pylint: disable=unused-argument
) -> None:
    """Handles modifications to HTML page metadata, e.g. canonical URLs.

    Args:
        docname:
            Basically the relative path to the doc, except `.rst` is omitted
            from the filename. E.g. `pw_string/docs`.
        context:
            A dict containing the HTML page's metadata.

    Returns:
        None. Modifications happen to the HTML metadata in-place.
    """
    canonical_url_key = 'pageurl'
    if context is None or canonical_url_key not in context:
        return
    canonical_url = context[canonical_url_key]
    context[canonical_url_key] = fix_canonical_url(canonical_url)


def add_links(module_name: str, toctree: Element) -> None:
    """Adds source code and issues URLs to a module's table of contents tree.

    This function is how we auto-generate the source code and issues URLs
    that appear for each module in the pigweed.dev site nav.

    Args:
        module_name:
            The Pigweed module that we're creating links for.
        toctree:
            The table of contents tree from that module's homepage.

    Returns:
        `None`. `toctree` is modified in-place.
    """
    src = ('Source code', cs_url(module_name))
    issues = ('Issues', issues_url(module_name))
    # Maintenance tip: the trick here is to create the `toctree` the same way
    # that Sphinx generates it. When in doubt, enable logging in this file,
    # manually modify the `.. toctree::` directive on a module's homepage, log
    # out `toctree` from somewhere in this script (you should see an XML-style
    # node), and then just make sure your code modifies the `toctree` the same
    # way that Sphinx generates it.
    toctree['entries'] += [src, issues]
    toctree['rawentries'] += [src[0], issues[0]]


def find_first_toctree(doctree: Document) -> Optional[Element]:
    """Finds the first `toctree` (table of contents tree) node in a `Document`.

    Args:
        doctree:
            The content of a doc, represented as a tree of Docutils nodes.

    Returns:
        The first `toctree` node found in `doctree` or `None` if none was
        found.
    """
    for node in doctree.traverse(nodes.Element):
        if node.tagname == 'toctree':
            return node
    return None


def parse_module_name(docname: str) -> str:
    """Extracts a Pigweed module name from a Sphinx docname.

    Preconditions:
        `docname` is assumed to start with `pw_`. I.e. the docs are assumed to
        have a flat directory structure, where the first directory is the name
        of a Pigweed module.

    Args:
        docname:
            Basically the relative path to the doc, except `.rst` is omitted
            from the filename. E.g. `pw_string/docs`.

    Returns:
        Just the Pigweed module name, e.g. `pw_string`.
    """
    tokens = docname.split('/')
    return tokens[0]


def on_doctree_read(app: Sphinx, doctree: Document) -> None:
    """Event handler that enables manipulating a doc's Docutils tree.

    Sphinx fires this listener after it has parsed a doc's reStructuredText
    into a tree of Docutils nodes. The listener fires once for each doc that's
    processed.

    In general, this stage of the Sphinx event lifecycle can only be used for
    content changes that do not affect the Sphinx build environment [1]. For
    example, creating a `toctree` node at this stage does not work, but
    inserting links into a pre-existing `toctree` node is OK.

    Args:
        app:
            Our Sphinx docs build system.
        doctree:
            The doc content, structured as a tree.

    Returns:
        `None`. The main modifications happen in-place in `doctree`.

    [1] See link in `on_source_read()`
    """
    docname = app.env.docname
    if not is_module_homepage(docname):
        return
    toctree = find_first_toctree(doctree)
    if toctree is None:
        # `add_toctree_to_module_homepage()` should ensure that every
        # `pw_*/docs.rst` file has a `toctree` node but if something went wrong
        # then we should bail.
        sys.exit(f'[module_metadata.py] error: toctree missing in {docname}')
    module_name = parse_module_name(docname)
    add_links(module_name, toctree)


def is_module_homepage(docname: str) -> bool:
    """Determines if a doc is a module homepage.

    Any doc that matches the pattern `pw_*/docs.rst` is considered a module
    homepage. Watch out for the false positive of `pw_*/*/docs.rst`.

    Preconditions:
        `docname` is assumed to start with `pw_`. I.e. the docs are assumed to
        have a flat directory structure, where the first directory is the name
        of a Pigweed module.

    Args:
        docname:
            Basically the relative path to the doc, except `.rst` is omitted
            from the filename.

    Returns:
        `True` if the doc is a module homepage, else `False`.
    """
    tokens = docname.split('/')
    if len(tokens) != 2:
        return False
    if not tokens[0].startswith('pw_'):
        return False
    if tokens[1] != 'docs':
        return False
    return True


def add_toctree_to_module_homepage(docname: str, source: str) -> str:
    """Appends an empty `toctree` to a module homepage.

    Note that this function only needs to create the `toctree` node; it doesn't
    need to fully populate the `toctree`. Inserting links later via the more
    ergonomic Docutils API works fine.

    Args:
        docname:
            Basically the relative path to `source`, except `.rst` is omitted
            from the filename.
        source:
            The reStructuredText source code of `docname`.

    Returns:
        For module homepages that did not already have a `toctree`, the
        original contents of `source` plus an empty `toctree` is returned.
        For all other cases, the original contents of `source` are returned
        with no modification.
    """
    # Don't do anything if the page is not a module homepage, i.e. its
    # `docname` doesn't match the pattern `pw_*`/docs`.
    if not is_module_homepage(docname):
        return source
    # Don't do anything if the module homepage already has a `toctree`.
    if '.. toctree::' in source:
        return source
    # Append an empty `toctree` to the content.
    # yapf: disable
    return (
        f'{source}\n\n'
        '.. toctree::\n'
        '   :hidden:\n'
        '   :maxdepth: 1\n'
    )
    # yapf: enable
    # Python formatting (yapf) is disabled in the return statement because the
    # formatter tries to change it to a less-readable single line string.


# inclusive-language: disable
def on_source_read(
    app: Sphinx,  # pylint: disable=unused-argument
    docname: str,
    source: List[str],
) -> None:
    """Event handler that enables manipulating a doc's reStructuredText.

    Sphinx fires this event early in its event lifecycle [1], before it has
    converted a doc's reStructuredText (reST) into a tree of Docutils nodes.
    The listener fires once for each doc that's processed.

    This is the place to make docs changes that have to propagate across the
    site. Take our use case of adding a link in the site nav to each module's
    source code. To do this we need a `toctree` (table of contents tree) node
    on each module's homepage; the `toctree` is where we insert the source code
    link. If we try to dynamically insert the `toctree` node via the Docutils
    API later in the event lifecycle, e.g. during the `doctree-read` event, we
    have to do a bunch of complex and fragile logic to make the Sphinx build
    environment [2] aware of the new node. It's simpler and more reliable to
    just insert a `.. toctree::` directive into the doc source before Sphinx
    has processed the doc and then let Sphinx create its build environment as
    it normally does. We just have to make sure the reStructuredText we're
    injecting into the content is syntactically correct.

    Args:
        app:
            Our Sphinx docs build system.
        docname:
            Basically the relative path to `source`, except `.rst` is omitted
            from the filename.
        source:
            The reStructuredText source code of `docname`.

    Returns:
        None. `source` is modified in-place.

    [1] www.sphinx-doc.org/en/master/extdev/appapi.html#sphinx-core-events
    [2] www.sphinx-doc.org/en/master/extdev/envapi.html
    """
    # inclusive-language: enable
    # If a module homepage doesn't have a `toctree`, add one.
    source[0] = add_toctree_to_module_homepage(docname, source[0])


def setup(app: Sphinx) -> Dict[str, bool]:
    """Hooks the extension into our Sphinx docs build system.

    This runs only once per docs build.

    Args:
        app:
            Our Sphinx docs build system.

    Returns:
        A dict that provides Sphinx info about our extension.
    """
    # Register the `.. pigweed-module::` and `.. pigweed-module-subpage::`
    # directives that are used on `pw_*/*.rst` pages.
    app.add_directive('pigweed-module', PigweedModuleDirective)
    app.add_directive('pigweed-module-subpage', PigweedModuleSubpageDirective)
    # inclusive-language: disable
    # Register the Sphinx event listeners that automatically generate content
    # for `pw_*/*.rst` pages:
    # www.sphinx-doc.org/en/master/extdev/appapi.html#sphinx-core-events
    # inclusive-language: enable
    app.connect('source-read', on_source_read)
    app.connect('doctree-read', on_doctree_read)
    app.connect('html-page-context', on_html_page_context)
    return {
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
