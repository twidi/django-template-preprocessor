(function($) {
    function create_highlighter()
    {
        var last_overlays= undefined;

        function _highlight(element) {
            $('.tp-highlight-overlay, .tp-label').remove();

            // Highlight this node with a black transparent rectangle.
            element.each(function() {
                var overlay = $('<div class="tp-highlight-overlay" />');
                overlay.css({
                    'left': $(this).offset().left,
                    'top': $(this).offset().top,
                    'width': $(this).outerWidth(),
                    'height': $(this).outerHeight()
                    });
                // Add tagname label above highlighting.
                $(body).append(
                        $('<p class="tp-label"/>')
                        .text('<' + $(this).get(0).tagName.toLowerCase() + ' />')
                        .css({
                            'left': $(this).offset().left,
                            'top': $(this).offset().top - 20
                            })
                        );

                // Hide overlays when mouse moves over it
                overlay.mouseover(function() { _highlight($()); });
                $('body').append(overlay);
            });
        }
        return _highlight;
    }
    var highlighter = create_highlighter();


    // Highlight template parts (EXPERIMENTAL)
    function highlightTemplateParts()
    {
        function removeHighlighting() {
            $('.tp-highlight-overlay, .tp-label, .tp-part, .tp-part-label').remove();
        }
        removeHighlighting();

        function process(node, parent_template, zIndex)
        {
            node.children().each(function() {
                var template = $(this).attr('d:t');
                var newIndex = zIndex;

                if (template && template != parent_template)
                {
                    newIndex ++;

                    // Create overlay
                    $(body).append(
                            $('<div class="tp-part tp-index-' + zIndex + '" />')
                            .css({
                                'left': $(this).offset().left,
                                'top': $(this).offset().top,
                                'width': $(this).outerWidth(),
                                'height': $(this).outerHeight(),
                                'z-index': 10000 + zIndex
                                })
                            .attr('title', template)
                            .click(removeHighlighting)
                            );

                    // Add label above highlighting.
                    $(body).append(
                            $('<p class="tp-part-label tp-index-' + zIndex + '" />')
                            .text(template)
                            .attr('title', template)
                            .css({
                                'left': $(this).offset().left,
                                'top': $(this).offset().top - 20
                                })
                            );
                }

                process($(this), (template ? template : parent_template), newIndex);
            });
        }
        var body = $('body');
        var template = body.attr('d:t');

        process(body, template, 0);
    }

    // Keep track of the current mouse position
    var current_element = ($('body').attr('d:s') ? $('body') : undefined);
    $('*').mouseover(function() {
        if ($(this).attr('d:s'))
        {
            // Remember element
            current_element = $(this);
            return false;
        }
    });

    // For a node reference number find the html node with this number.
    function get_ref(ref_number)
    {
        return $('*[d\\:r=' + ref_number + ']');
    }

    function getElementInfo(element)
    {
        return {
                "template": element.attr('d:t'),
                "line": element.attr('d:l'),
                "column": element.attr('d:c'),
                "ref": element.attr('d:r'),
                "tagname": (element.get(0) ? element.get(0).tagName.toLowerCase() : undefined),
            };
    }

    // Returns an array of the ref ids of the parents of this node
    function getParents(element)
    {
        var parents = [];
        element.parents().each(function() {
                if ($(this).attr('d:r') && $(this).attr('d:s'))
                    parents.push($(this).attr('d:r'));
                });
        parents.reverse();
        return parents;
    }

    chrome.extension.onRequest.addListener(function(request, sender, sendResponse) {
            if(request['action'] == "highlight-template-parts")
            {
                highlightTemplateParts();
                sendResponse({"result": "ok"});
            }
            else if (request['action'] == 'get-template-info')
            {
                if (current_element)
                    sendResponse(getElementInfo(current_element));
                else
                    sendResponse({ });
            }
            else if (request['action'] == 'get-ref-source')
            {
                var ref = get_ref(request['ref']);
                if (ref.length)
                    sendResponse($.parseJSON(ref.eq(0).attr('d:s')));
                else
                    sendResponse([ ]);
            }
            else if (request['action'] == 'get-ref-info')
            {
                var ref = get_ref(request['ref']);
                if (ref.length)
                    sendResponse(getElementInfo(ref.eq(0)));
                else
                    sendResponse({ });
            }
            else if (request['action'] == 'get-ref-parents')
            {
                var ref = get_ref(request['ref']);
                if (ref.length)
                    sendResponse(getParents(ref.eq(0)));
                else
                    sendResponse({ });
            }
            else if (request['action'] == 'highlight-ref')
            {
                var ref = get_ref(request['ref']);

                if (ref)
                    highlighter(ref);
                sendResponse({ });
            }
            else
                sendResponse({ });
    });
})(jQuery);
