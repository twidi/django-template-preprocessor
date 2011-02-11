
-----------------------------------------------------------
Template Preprocessor Readme
-----------------------------------------------------------

Author: Jonathan Slenders, City Live






Why?
*****************

- Templates contain a lot of meaningless information causing more
  bandwidth than required.
- A lot of information in templates which appears to be dynamic is
  actually static and only needs to be calculated once instead of
  for every single request.


How?
*****************

- Parse template, extract useful information, drop the rest and compile.

What can we preprocess?
- URLs when they don't take any parameters.
- {% trans %} and {% transblock %} when they don't take parameters
- {% callmacro %}, {% now "Y" %}
- {% tabpage %}, {% tabs %} and {% tabcontent %}
- {% google_analytics ... %}

What can we compress?
- Remove whitespace:
    * between html tags (Not in <pre> and <textarea>, for the rest: keep always
      at least one space, except around block-level html tags)
    * between html attributes
    * in Javascript
    * in css
- Remove empty attributes if allowed: like class=""
- Comments in Javascript code. ( // and /*...*/ )
- Comments in CSS code. ( /* ... */ )
- Merge all CSS into the first <style> node.
- Remove {% compress %} (compress shouldn't be at runtime)
- Merge all javascript code into the first <script> node. (unless the script
  appears in a conditional comment) 

Compile:
- Django template inheritance:
    - merge templates with the parent from which it extends. (If they're
      merged, we don't need {% block %} tags anymore....)
    - Include {% include %} blocks.
    - Fill in {{ block.super }} by the parent block's content.
    - Merge all {% load %} statements in one.
- Javascript code (rename variables to be as short as possible, remove comments
  and whitespace where it's allowed.)


Integration with Django:
- As a template loader.
- Preprocess once, return preprocessed template as string or Template object.


The difficult part here is that templates consist of several languages,
processed in following order:
- Django Template Tags
- HTML/XHTML tags
- Embedded Javascript & CSS code.
And Django is not really aware of which code is actually HTML and which is not.

So, we need a parser to parse the templates in the same order as in which they
are processed. But we can't preprocess all Django Tags without having a
{context}, so we have to parse all other languages inside a parse tree of
django code.


How the parser works
******************

1. Parsing Django template tags:
   - lexing & parsing of the source code returns parse tree consisting of
     DjangoContent (which is either html, plain text or anything else, django
     is not aware of it) and DjangoTemplateTags.


2. If HTML parsing is enabled.
    - For every content node in the previous parse tree, parse it as if it is
      HTML content. The result is a new parse tree containing, where the
      DjangoContent nodes are replaced by HtmlTags and HtmlAttributes.
      (and a HtmlAttributes or -Tag may contain a DjangoTag again, and so on....)

        hard example, but still supported:
            <span class="{% if test %}selected"> .... </span>


3. If JS parsing is enabled.
    - For all HtmlTag elements in the tree, find those with 'script' as name,
      and parse it's content again with a Javascript lexer/parser.

      again, nesting lanugages is still possible

        <script type="text/javascript">// <[!CDATA[
            alert('{% url ... %}'); // ]]>
        </script>

4. If CSS parsing is enabled:
    - similar to JS parsing.


5. Compile Javascript:
    - Create symbol table for every scope. (scope is surrounded by curly brackets.)
    - Rename variables in private scopes to be as short as possible.

For debugging, the output is also written to the 'processed_template' directory.


Configuration
******************

In settings.py:

        # Move the original template loaders in here
        ORIGINAL_TEMPLATE_LOADERS = (
            'django.template.loaders.filesystem.load_template_source',
            'django.template.loaders.app_directories.load_template_source',
        )
        
        # The new template loader will wrap around the original loaders.
        TEMPLATE_LOADERS = (
            'template_preprocessor.template.loaders.preprocess.load_template_source',
        )

        # Cache directory where compiled files are saved. Alse useful for debugging.
        TEMPLATE_CACHE_DIR = ROOT + 'processed_templates'
        
        # Add to installed apps
        INSTALLED_APPS += ( 'template_preprocessor', )
        
        
        # Optional (for the management command `preprocess_all_templates` only)
        # May be useful for a self-test.
        TEMPLATE_PREPROCESS = (
            # Source dir -> destination dir
            (ROOT + 'templates', ROOT + 'processed_templates'),
        )


Configuration at runtime
******************
    Following template tag is an example of how to alter the preprocessor
    behaviour for a specific template.

    {% load template_preprocessor %}{% ! no-html %}


Faster?
******************

Some of our test show page loading improvements op to 400% compared to the
default Django loader, and up to 200% compared to the cached loader in Django
1.2.



Recommendations
******************

* Use <style type="text/css"> in included templates, not in base.html. (Keep
  syntax highlighting, and will be berged anyway.

* Use CDATA for javascript. (will avoid accidently Html tags in script.)
    <script type="text/javascript">// <![CDATA[ 
        ...alert('<div>');
        // ]]>
    </script>

* Prefer javascript comments in JS code above Django comments, and use CSS
  comments in CSS code.

* _Most_ important: _always_ open and close HTML tags, javascript braces, etc..
  in the same scope. Instead of:

            {% if test %}
                <a ...
            {% else test %}
                <a ...
            {% endif %}
                ...
            > link </a>


  do:

            <a
            {% if test %}
                 ...
            {% else test %}
                 ...
            {% endif %}
                ...
            > link </a>

  See? Opening bracket is now in the same text node as the closing bracket.
  This is important for the parser to know that they are a pair, because the
  HTML parser won't or can't be aware of how the Django Template tags are
  rendered. What if the render() method of the {%if%}-node would return an
  empty string, then there's no pair to be found in the first example.


TODO's
*********************

- Removal of HTML comments
- Adding of alt="" for images. (and output warning somewhere if missing alt was
  found.
- Output warnings if double quotes around attributes are missing.



