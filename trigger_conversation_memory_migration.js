// Trigger conversation_memory table migration from CRM browser console
// Instructions:
// 1. Open https://mortgage-crm-nine.vercel.app
// 2. Login to your account
// 3. Press F12 to open DevTools
// 4. Click the Console tab
// 5. Copy and paste this entire script
// 6. Press Enter

(async function() {
    try {
        console.log('🔄 Running conversation_memory table migration...');

        const response = await fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/migrations/add-conversation-memory', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token').replace(/"/g, '')}`,
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success || response.ok) {
            console.log('✅ Migration completed!');
            console.log(data);

            if (data.already_exists) {
                alert(`✅ Migration already complete!\n\nThe conversation_memory table already exists.\nCurrent rows: ${data.row_count}\n\nThe AI Memory System is ready to use!`);
            } else {
                alert(`✅ Migration successful!\n\n${data.message}\n\nThe AI Memory System is now ready!\n\nYou can now use the Smart AI Chat in the Lead Detail page.`);
            }
        } else {
            console.error('❌ Migration failed');
            console.error(data);
            alert('❌ Migration failed:\n\n' + (data.detail || data.message || data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('❌ Error running migration:', error);
        alert('❌ Error: ' + error.message);
    }
})();
