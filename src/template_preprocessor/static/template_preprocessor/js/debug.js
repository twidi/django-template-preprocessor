/*
 * Debug utilities for debugging templates which are compiled with debug
 * symbols.
 *
 * Author: Jonathan Slenders, CityLive
 *
 * Depends on the JQuery library
 */




// Show hierarchy
(function() {
    function highlightTemplateParts()
    {
        function process(node, parent_template)
        {
            node.children().each(function() {
                var template = $(this).attr('d:t');

                if (template && template != parent_template)
                {
                    var wrapper = $(this).css('display') == 'inline' ?
                            $('<span class="tp-wrapper" />') : $('<p class="tp-wrapper" />') ;

                    // Use for the wrapper the same display method as the current
                    // element
                    wrapper.css('display', $(this).css('display'));

                    // Apply wrapper around element
                    $(this).wrap(wrapper);
                    $(this).prepend($('<p class="tp-template"/>').text(template));
                }

                process($(this), (template ? template : parent_template));
            });
        }
        var body = $('body');
        var template = body.attr('d:t');

        process(body, template);
    }
    $(document).keypress(function(e) {
        if (e.charCode == 104) // 'h' key
            highlightTemplateParts();
    });
})();


(function() {
    // Highlighting of elements. Calling this method again will remove the
    // highlighting of the last element.
    function create_highlighter(classname)
    {
        var last_highlight = undefined;

        function _highlight(element) {
            if (last_highlight)
                last_highlight.removeClass(classname);
            element.addClass(classname);

            last_highlight = element;
        }
        return _highlight;
    }
    var highlightHtml = create_highlighter('tp-highlight-html');
    var highlightSource = create_highlighter('tp-highlight-source');


    function statusBar()
    {
        var body = $('body');

        // Insert debug container into html body
        var tag_name = $('<span/>');
        var tag_position = $('<span/>');

        var debug_container = $('<p class="tp-debug-container"/>')
                                    .append(tag_name)
                                    .append(tag_position)
                                    .hide();

        body.append(debug_container);

        // Show element information in status bar
        this.showElementInfo = function(element)
        {
            tag_position.empty();
            tag_position.append($('<strong/>').text(element.attr('d:t')));
            tag_position.append($('<span/>').text(
                    ' Line: ' +
                    element.attr('d:l') +
                    ' Column: ' +
                    element.attr('d:c')));
            tag_name.text(' <' + (element.get(0) ? element.get(0).tagName.toLowerCase() : '...') + '/> ');

            debug_container.show();
        }
    }

    var status_bar = new statusBar();

    // For every possible HTML tag in body:
    $('*').mouseover(function() {
        if ($(this).attr('d:s'))
        {
            var refNumber = $(this).attr('d:ref');
            //status_bar.showElementInfo($(this));
            //highlightHtml($(this));
            highlightRef(refNumber);
            return false;
        }
    });

    // For a node reference number find:
    //      - the html node with this number.
    function get_ref(ref_number)
    {
        return $('*[d\\:ref=' + ref_number + ']');
    }
    //      - the source code node with this number.
    function get_source_ref(ref_number)
    {
        return sourceBrowser.source_container.find('*[d\\:source-ref=' + ref_number + ']');
    }

    function highlightRef(ref_number)
    {
        // Highlight in source code
        highlightSource(get_source_ref(ref_number));
        highlightHtml(get_ref(ref_number));
        status_bar.showElementInfo(get_ref(ref_number).eq(0));
    }

    function create_source_display_span(element)
    {
        // Create new div for displaying this source code
        var source_code = element.attr('d:s');

        if (! source_code)
            return $('<span class="tp-node-not-rendered">').text('Node not rendered in output...');

        // Parse source code from JSON
        function parse(source, type)
        {
            var span = $('<span/>');
            if (type)
                span.addClass('tp-type-' + type);

            for (var e in source)
            {
                var part = source[e];

                if (typeof(part) == 'string')
                    span.append($('<span/>').text(part));
                else
                {
                    if ("include" in part)
                    {
                        var refNumber = part['include'];

                        (function(refNumber) {
                            // Create child
                            var child = $('<span class="tp-child" />');
                            child.attr('d:source-ref', refNumber);

                            // Hover over the child will highlight all the matching references.
                            child.mouseover(function() {
                                    highlightRef(refNumber);
                                    return false;
                                });

                            // Child source code
                            child.append(create_source_display_span(get_ref(refNumber).eq(0)));

                            // Add expand/collapse button
                            var expand = $('<span class="tp-expand-button" />').text(' - ');
                            var visible = true;
                            expand.click(function() {
                                    visible = !visible;
                                    if (visible)
                                    {
                                        child.show();
                                        expand.text(' - ');
                                    }
                                    else
                                    {
                                        child.hide();
                                        expand.text(' + ');
                                    }
                                    return false;
                                    });

                            span.append(expand);
                            span.append(child);
                        })(refNumber);
                    }
                    else
                    {
                        var type = part['type'];
                        var content = part['content'];
                        span.append(parse(content, type));
                    }

                }
            }
            return span;
        }
        return parse($.parseJSON(source_code));
    }

    function sourceBrowser() {
        // Create source container
        var container = $('<pre class="tp-source"/>').hide();
        $('body').append(container);

        // Create titlebar
        var title_bar = $('<p class="tp-source-header"/>').text('test');

        // Source container
        this.source_container = $('<pre />');

        // Footer
        var footer = $('<p class="tp-source-footer"/>');
        var close_button = $('<input type="button" value="Close" />');
        var detach_button = $('<input type="button" value="Detach" />');
        var attach_button = $('<input type="button" value="Attach" />').hide();
        footer.append(detach_button).append(attach_button).append(close_button);

        container.append(title_bar);
        container.append(this.source_container);
        container.append(footer);

        // Handle close button
        close_button.click(function() {
                if (is_external)
                    attach_button.click();
                container.hide();
            });

        var is_external = false;
        this.is_external = function() { return is_external; };

        // Handle detach button
        detach_button.click(detach);
        function detach()
        {
            is_external = true;

            // Create window
            var w = window.open('', 'Django source code', 'scrollbars=yes,toolbars=no,menubar=no,location=no,resizable=yes,status=no,width=800,height=600');
            _tp_source_window = w;
            w.document.open();
            w.document.write(
                '<html>' +
                '<head><link type="text/css" rel="stylesheet" href="/static/template_preprocessor/css/debug.css" /></head>' +
                '<body class="tp-external-source"></body>' +
                '<html>');
            w.document.close();

            // Move source control to this window
            container.detach();
            $(w.document).find('body').append(container);

            // Detach handler
            detach_button.hide();
            attach_button.show();
            attach_button.unbind('click').click(function() {
                    attach();
                    w.close();
                    return false;
                });

            // Attach window again when pop-up has been closed, or when
            // attach button has been clicked.
            $(w).unload(attach);

            return false
        }
        function attach()
        {
            is_external = false;

            // Move source control back
            container.detach();
            $('body').append(container);
            container.show();

            // Rename attach/detach button
            attach_button.hide();
            detach_button.show();

            return false;
        }

        this.toggle = function() { container.toggle(); };

        this.showElement = function(element) {
            this.source_container.empty();
            this.source_container.append(create_source_display_span(element));

            title_bar.empty();

            title_bar.append($('<span/>').text('Showing source of: '));
            title_bar.append($('<strong/>').text(element.attr('d:t')));
            title_bar.append($('<span/>').text(' <' + (element.get(0) ? element.get(0).tagName.toLowerCase() : '...') + '/> '));
            title_bar.append($('<em/>').text(
                    ' Line: ' +
                    element.attr('d:l') +
                    ' Column: ' +
                    element.attr('d:c')));
        };
    }

    var sourceBrowser = new sourceBrowser();

    // Hovering over any HTML element, will mark this as current element
    var current_element = undefined;
    $('*').mouseover(function() {
        if ($(this).attr('d:s'))
            current_element = $(this);
    });
    $(document).keypress(function(e) {
        if (e.charCode == 115 && current_element) // 's' key
            sourceBrowser.showElement(current_element);

            if (! sourceBrowser.is_external())
                sourceBrowser.toggle();
    });
 })();
