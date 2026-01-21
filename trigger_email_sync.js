// Trigger email sync from CRM browser console
// Instructions:
// 1. Open https://mortgage-crm-nine.vercel.app
// 2. Login to your account
// 3. Press F12 to open DevTools
// 4. Click the Console tab
// 5. Copy and paste this entire script
// 6. Press Enter

(async function() {
    try {
        console.log('🔄 Triggering email sync...');

        const response = await fetch('https://app.perenniaai.com/api/v1/email/sync-now', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token').replace(/"/g, '')}`,
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success || response.ok) {
            console.log('✅ Email sync completed!');
            console.log(data);
            alert(`✅ Email sync completed!\n\n${data.message || 'Emails synced successfully'}\n\nGo to Reconciliation Center to see the new tasks.`);
        } else {
            console.error('❌ Email sync failed');
            console.error(data);
            alert('❌ Email sync failed:\n\n' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('❌ Error triggering email sync:', error);
        alert('❌ Error: ' + error.message);
    }
})();
