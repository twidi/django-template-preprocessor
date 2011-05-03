"""
Generate a graph of all the templates.

- Dotted arrows represent includes
- Solid arrows represent inheritance.

"""


from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils.html import escape
from optparse import make_option
from yapgvb import Graph
import datetime
import time
import math
import os

from django.contrib.auth.models import User
from django.db.models import Q
from template_preprocessor.utils import template_iterator, get_template_path
from django.conf import settings


class Command(BaseCommand):
    help = "Make dependency graph"
    option_list = BaseCommand.option_list + (
        make_option('--directory', action='append', dest='directory', help='Template directory (all templates if none is given)'),
        make_option('--exclude', action='append', dest='exclude_directory', help='Exclude template directory'),
    )

    def handle(self, *args, **options):
        directory = (options.get('directory', ['']) or [''])[0]
        exclude_directory = (options.get('exclude_directory', []) or [])

        g = Graph('Template dependencies', True)

        g.layout('neato')
        g.landscape = True
        g.rotate = 90
        g.label = str(datetime.datetime.now())
        #g.scale = 0.7
        #g.overlap = 'prism'
        #g.overlap = False
        g.overlap = 'scale'
        g.ranksep = 1.8
        g.overlap = 'compress'
        g.ratio = 1. / math.sqrt(2)
        g.sep = 0.1
        g.mindist = 0.1

        nodes = set()
        edges = [ ]
        nodes_in_edges = set()

        # Retreive all nodes/edges
        for dir, t in template_iterator():
            if t.startswith(directory) and not any([ t.startswith(x) for x in exclude_directory ]):
                nodes.add(t)

                # {% include "..." %}
                includes = self._make_output_path(t) + '-c-includes'

                if os.path.exists(includes):
                    for t2 in open(includes, 'r').read().split('\n'):
                        if t2:
                            nodes.add(t2)
                            edges.append( (t, t2, False) )

                            nodes_in_edges.add(t)
                            nodes_in_edges.add(t2)

                # {% extends "..." %}
                extends = self._make_output_path(t) + '-c-extends'

                if os.path.exists(extends):
                    for t2 in open(extends, 'r').read().split('\n'):
                        if t2:
                            nodes.add(t2)
                            edges.append( (t, t2, True) )

                            nodes_in_edges.add(t)
                            nodes_in_edges.add(t2)

        # Remove orphan nodes
        for n in list(nodes):
            if not n in nodes_in_edges:
                nodes.remove(n)

        # Create graphvis nodes
        nodes2 = { }
        for t in nodes:
            node = self._create_node(t, g, nodes2)

        # Create graphvis edges
        for t1, t2, is_extends in edges:
            print 'from ', t1, ' to ', t2
            node_a = self._create_node(t1, g, nodes2)
            node_b = self._create_node(t2, g, nodes2)
            edge = g.add_edge(node_a, node_b)
            edge.color = 'black'
            edge.arrowhead = 'normal'
            edge.arrowsize = 1.1
            if is_extends:
                edge.style = 'solid'
            else:
                edge.style = 'dotted'

        #g.layout('neato')
        g.layout('twopi')
        g.render(settings.ROOT + 'template_dependency_graph.pdf', 'pdf', None)
        g.render(settings.ROOT + 'template_dependency_graph.jpg', 'jpg', None)


    def _create_node(self, template, graph, nodes):
        """
        Create node for subscription, if one exists for this subscription in
        `nodes`, return the existing.
        """
        if template not in nodes:
            node = graph.add_node(template.replace('/', '/\n').encode('utf-8'))
            node.shape = 'rect'
            node.label = template.replace('/', '/\n').encode('utf-8')
            node.fontsize = 11
            node.fixedsize = False
            node.width = 1.0
            node.height = 0.8
            node.fontcolor = 'black'


            node.style = 'filled'
            node.fillcolor = 'white'
            node.fontcolor = 'black'

            nodes[template] = node

        return nodes[template]

    def _make_output_path(self, template):
        return os.path.join(settings.TEMPLATE_CACHE_DIR, 'en', template)

