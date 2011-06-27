/*
 * Django Template Debugger script.
 *
 */

(function() {

    // ============== Create source window ==================

    // Read css file through ajax. (We cannot link this css from inside the
    // window because it runs with different permissions.)
    var css = '';
    $.ajax({
                'type': 'text',
                'url': chrome.extension.getURL('source-browser.css'),
                'success': function(result) { css = result; }
            });

    function createWindow() {
        var w = window.open('about:blank', 'Django source code',
                'scrollbars=yes,toolbars=no,menubar=no,location=no,resizable=yes,status=no,width=800,height=600');

        w.document.open();
        w.document.write(
            '<html>' +
            '<head>' +
            '  <title>Django source code</title>' +
            '  <style type="text/css">' + css + '</style>' +
            '</head>' +
            '<body></body>' +
            '<html>');
        w.document.close();
        w.document.title = 'Django source browser';

        return w;
    }



    // ============== API to content script ==================

    function getCurrentRefInfo(tab, callback)
    {
        chrome.tabs.sendRequest(tab.id, { "action": "get-template-info" }, callback);
    }

    function getRefObject(tab, ref, callback)
    {
        // get source
        chrome.tabs.sendRequest(tab.id,
            {
                    "action": "get-ref-source",
                    "ref": ref
            },
            callback);
    }

    function getRefInfo(tab, ref, callback)
    {
        // get source
        chrome.tabs.sendRequest(tab.id,
            {
                    "action": "get-ref-info",
                    "ref": ref
            },
            callback);
    }

    function getParents(tab, ref, callback)
    {
        // get source
        chrome.tabs.sendRequest(tab.id,
            {
                    "action": "get-ref-parents",
                    "ref": ref
            },
            callback);
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


    // ============== - ==================

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


    // ============== - ==================

    function sourceBrowser() {
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

        this.showElement = function(info, breadcrumbs, element) {
            this.source_container.empty();
            this.source_container.append(element);

            title_bar.empty();

            title_bar.append($('<span/>').text('Showing source of: '));
            title_bar.append($('<strong/>').text(info["template"]));
            title_bar.append($('<span/>').text(' <' + (info["tagname"] || '...' ) + '/> '));
            title_bar.append($('<em/>').text(
                    ' Line: ' + info["line"] + ' Column: ' + info["column"]));
            title_bar.append($('<br/>'));
            title_bar.append(breadcrumbs);

            var path = $('<span class="path" />');

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
            getRefInfo(tab, ref, function(data) {
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
                            getRefObject(tab, refNumber, function(response) {
                                child.append(create_source_display_span(tab, refNumber, response));
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

    function createBreadCrumbs(tab, ref)
    {
        var span = $('<span class="breadcrumbs" />');
        getParents(tab, ref, function(response) {
            for (var i in response)
            {
                (function(ref) {
                    var s = $('<span/>');
                    s.click(function(){
                        viewRefSource(tab, ref);
                        return false;
                    });
                    getRefInfo(tab, ref, function(data) {
                        s.text('<' + data['tagname'] + '> ');
                        s.attr('title', data['template'] + ' (line ' + data['line'] +
                            ', column ' + data['column'] + ')');
                    });
                    span.append(s);
                })(response[i]);
            }
        });
        return span;
    }

    function viewRefSource(tab, ref)
    {
        getRefInfo(tab, ref, function(info) {
            getRefObject(tab, ref, function(response) {
                getBrowser().showElement(info,
                            createBreadCrumbs(tab, ref),
                            create_source_display_span(tab, ref, response));
                highlightRef(tab, ref);
            });
        });
    }

    function viewTabSource(tab)
    {
        getCurrentRefInfo(tab, function(response) {
            var ref = response['ref'];
            viewRefSource(tab, ref);
        });
    }


    // ===================== Menu callbacks ===========================

    function viewDjangoSource(info, tab) {
        viewTabSource(tab);
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
