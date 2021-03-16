/* This function assigns onclick event handlers to data rows for tables
*   tableId: The id assigned to the table in definition @ tables.py
*   rowAttribute: The row attribute where we store the id for the detail page
*   url: The relative url for the details page of the record we want to redirect to when row clicked */
function addRowHandlers(tableId, rowAttribute, url) {
    let table = document.getElementById(tableId);
    let rows = table.getElementsByTagName("tr");
    for (let i = 0; i < rows.length; i++) {
        let currentRow = table.rows[i];
        let createClickHandler =
            function (row) {
                return function () {
                    let id = row.attributes[rowAttribute].value;
                    window.location = url + id;
                };
            };
        currentRow.onclick = createClickHandler(currentRow);
    }
}

/* Callers of this script need to have the script tag defined below as well as
    provide the arbitrary data attributes  */
let script_tag = document.getElementById("row-click-handler");
let tableId = script_tag.getAttribute("data-table-id");
let rowAttribute = script_tag.getAttribute("data-row-attribute");
let url = script_tag.getAttribute("data-url");
window.onload = addRowHandlers(tableId, rowAttribute, url);