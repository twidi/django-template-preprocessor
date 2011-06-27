/*
 * Django Template Debugger script.
 *
 */

(function() {

    function createWindow() {
        var w = window.open('about:blank', 'Django source code', 'scrollbars=yes,toolbars=no,menubar=no,location=no,resizable=yes,status=no,width=800,height=600');

        w.document.open();
        w.document.write(
            '<html>' +
            '<head>' +
            '  <title>Django source code</title>' +
            '  <link type="text/css" rel="stylesheet" href="source-browser.css" />' +
            '</head>' +
            '<body class="tp-external-source"></body>' +
            '<html>');
        w.document.close();
        w.document.title = 'Django source browser';

        return w;
    }



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

  function sourceBrowser() {
        // Create window
        var w = createWindow();

        // Create source container
        var container = $('<pre class="tp-source"/>');

        // Create titlebar
        var title_bar = $('<p class="tp-source-header"/>');

        // Source container
        this.source_container = $('<pre />');

        // Footer
        var footer = $('<p class="tp-source-footer"/>');
        footer.text('footer....');

        container.append(title_bar);
        container.append(this.source_container);
        container.append(footer);

        // Place container in new window
        $(w.document).find('body').append(container);


        this.showElement = function(info, element) {
            this.source_container.empty();
            this.source_container.append(element);

            title_bar.empty();

            title_bar.append($('<span/>').text('Showing source of: '));
            title_bar.append($('<strong/>').text(info["template"]));
            title_bar.append($('<span/>').text(' <' + (info["tagname"] || '...' ) + '/> '));
            title_bar.append($('<em/>').text(
                    ' Line: ' + info["line"] + ' Column: ' + info["column"]));
        };

        function get_ref(ref_number)
        {
            return $(w.document).find('*[d\\:ref=' + ref_number + ']');
        }

        var highlighter = create_highlighter('tp-highlight-html');
        this.highlightRef = function(refNumber) {
            highlighter(get_ref(refNumber));
        };

        this.isClosed = function() { return w.closed; };
    }


    var browser;

    function getBrowser()
    {
        if (! browser || browser.isClosed())
            browser = new sourceBrowser();
        return browser;
    }


    function getRefObject(tab, ref, callback)
    {
        // get source
        chrome.tabs.sendRequest(tab.id,
            {
                    "action": "get-ref-source",
                    "ref": ref
            },
            function(response) {
                callback(response);
            });
    }



    function highlightRef(tab, refNumber)
    {
        // Highlight ref in source browser
        browser.highlightRef(refNumber);

        // Send signal to original page to highlight itself.
        chrome.tabs.sendRequest(tab.id,
            {
                    "action": "highlight-ref", 
                    "ref": refNumber
            }, function(response) { });
    }


    function create_source_display_span(tab, ref, data)
    {
        // Parse source code from JSON
        function parse(source, type)
        {
            var span = $('<span/>');
            if (type)
                span.addClass('tp-type-' + type);

            // Hover will highlight all the matching references.
            span.mouseover(function() {
                    highlightRef(tab, ref);
                    return false;
                });

			// Set title attribute
			getRefObject(tab, ref, function(data) {
					// TODO: no getRefObject, use getRefInfo
					span.attr('title', data['template'] + ' (line ' + data['line'] +
							', column ' + data['column'] + ')');

				});

            // Add child nodes
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
                            child.attr('d:ref', refNumber);

                            // source code
                            getRefObject(tab, refNumber, function(data) {
                                child.append(create_source_display_span(tab, refNumber, data));
                            });

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
        return parse(data);
    }


    function viewDjangoSource(info, tab) {
        // Request position in template
        chrome.tabs.sendRequest(tab.id, { "action": "get-template-info" }, function(response) {
//alert(JSON.stringify(response));
                var ref = response['ref'];

                getRefObject(tab, ref, function(data) {
                    getBrowser().showElement(response, create_source_display_span(tab, ref, data));
					highlightRef(tab, ref);
                });
            });
    }

    function highlightTemplateParts(info, tab)
    {
        chrome.tabs.sendRequest(tab.id, { "action": "highlight-template-parts" }, function(response) {
        
            });
    }

    function editInEditor(info, tab)
    {
        chrome.tabs.sendRequest(tab.id, { "action": "get-template-info" }, function(response) {
                alert('TODO: edit: ' + response['template']);
        
            });
    }


    chrome.contextMenus.create({
            "title": "View Django Source Code",
            "contexts": [ "page", "selection", "image", "editable", "link" ],
            "onclick": viewDjangoSource
            });

    chrome.contextMenus.create({
            "title": "Edit Django template in editor",
            "contexts": [ "page", "selection", "image", "editable", "link" ],
            "onclick": editInEditor
            });


    chrome.contextMenus.create({
            "title": "Highlight template parts",
            "contexts": [ "page" ],
            "onclick": highlightTemplateParts
            });

})();
