(function($) {
    function create_highlighter(classname)
    {
        var last_overlays= undefined;

        function _highlight(element) {
            $('.tp-highlight-overlay').remove();

            // Experimental
            element.each(function() {
                var overlay = $('<div class="tp-highlight-overlay" />');
                overlay.css({
                    'position': 'absolute',
                    'border': '2px solid blue',
                    'background-color': '#6666ff',
                    '-webkit-opacity': '.4',
                    'left': $(this).offset().left,
                    'top': $(this).offset().top,
                    'width': $(this).outerWidth(),
                    'height': $(this).outerHeight(),
                    'z-index': '10000',
                    });
                $('body').append(overlay);
            });
        }
        return _highlight;
    }
    var highlighter = create_highlighter('tp-highlight');


    // Highlight template parts
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

    // Keep track of the current mouse position
    var current_element = undefined;
    $('*').mouseover(function() {
        if ($(this).attr('d:s'))
        {
            current_element = $(this);

            // TODO Don't do highlighting here: pass the hover event to the source browser, and have it callback
            var refNumber = $(this).attr('d:ref');

//            highlighter(get_ref(refNumber));

            return false;
        }
    });


    // For a node reference number find the html node with this number.
    function get_ref(ref_number)
    {
        return $('*[d\\:ref=' + ref_number + ']');
    }

    function getElementInfo(element)
    {
        return {
                "template": element.attr('d:t'),
                "line": element.attr('d:l'),
                "column": element.attr('d:c'),
                "ref": element.attr('d:ref'),
                "tagname": (element.get(0) ? element.get(0).tagName.toLowerCase() : undefined),
            };
    }

    // Returns an array of the ref ids of the parents of this node
    function getParents(element)
    {
        var parents = [];
        element.parents().each(function() {
                if ($(this).attr('d:ref'))
                    parents.push($(this).attr('d:ref'));
                });
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
                    sendResponse({ });
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
