// Run this in your CRM's browser console to trigger the migration
// Instructions:
// 1. Open https://mortgage-crm-nine.vercel.app
// 2. Login to your account
// 3. Press F12 to open DevTools
// 4. Click the Console tab
// 5. Copy and paste this entire script
// 6. Press Enter

(async function() {
    try {
        console.log('🔧 Running migration to add external_message_id column...');

        const response = await fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/migrations/add-external-message-id', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token').replace(/"/g, '')}`,
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            console.log('✅ Migration successful!');
            console.log(data);
            alert('✅ Migration completed successfully!\n\n' + data.message);
        } else {
            console.error('❌ Migration failed');
            console.error(data);
            alert('❌ Migration failed:\n\n' + (data.message || data.error));
        }
    } catch (error) {
        console.error('❌ Error running migration:', error);
        alert('❌ Error: ' + error.message);
    }
})();
