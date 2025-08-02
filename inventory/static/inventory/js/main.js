$(document).ready(function() {
    
    // Handles the mobile sidebar toggle
    $('#sidebar-toggle').on('click', function() {
        $('#sidebar').toggleClass('sidebar-closed');
        $('#main-content').toggleClass('main-content-expanded');
    });

    // Handles all collapsible submenus in the sidebar
    $('.submenu-toggle').on('click', function() {
        const submenu = $(this).next('.submenu');
        const icon = $(this).find('.fa-chevron-down');
        
        submenu.toggleClass('hidden');
        icon.toggleClass('rotate-180');
    });

});