window.onload = function() {
    document.body.onclick = function(e) {
        var spoiler_elem = e.target;
        if (spoiler_elem.className == 'spoiler'){
            spoiler_elem.classList = ['spoiler-show'];
        }
    }
}