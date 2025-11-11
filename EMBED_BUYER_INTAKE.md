# Buyer Intake Application - Embed Guide

## 🎨 Updated Color Scheme
The buyer intake application now matches your CRM's teal color scheme:
- Primary Color: #217F8D (Teal)
- Gradient: #217F8D → #1a6670
- All buttons, inputs, and accents use the CRM colors

---

## 📋 Embedding Options

### Option 1: Simple iFrame Embed (Recommended)

Copy and paste this code into your website's HTML:

```html
<!-- Full-width embed -->
<iframe
  src="https://mortgage-crm-nine.vercel.app/apply"
  width="100%"
  height="1200px"
  frameborder="0"
  style="border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
</iframe>
```

### Option 2: Responsive iFrame (Mobile-Friendly)

```html
<!-- Responsive container -->
<div style="max-width: 1000px; margin: 0 auto; padding: 20px;">
  <iframe
    src="https://mortgage-crm-nine.vercel.app/apply"
    width="100%"
    height="1200px"
    frameborder="0"
    style="border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); min-height: 800px;">
  </iframe>
</div>

<style>
  /* Mobile responsive */
  @media (max-width: 768px) {
    iframe {
      height: 1400px !important;
    }
  }
</style>
```

### Option 3: Full-Height Auto-Resize iFrame

Use this for automatic height adjustment based on content:

```html
<div id="buyer-intake-container" style="max-width: 1000px; margin: 0 auto; padding: 20px;">
  <iframe
    id="buyer-intake-frame"
    src="https://mortgage-crm-nine.vercel.app/apply"
    width="100%"
    height="1200px"
    frameborder="0"
    scrolling="no"
    style="border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
  </iframe>
</div>

<script>
  // Auto-resize iframe to content (works if same domain or CORS configured)
  window.addEventListener('message', function(e) {
    if (e.data && e.data.height) {
      document.getElementById('buyer-intake-frame').style.height = e.data.height + 'px';
    }
  });
</script>
```

### Option 4: Modal/Popup Embed

Great for "Apply Now" buttons on your site:

```html
<!-- Button to trigger modal -->
<button onclick="openBuyerIntake()" style="
  padding: 14px 32px;
  background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(33, 127, 141, 0.3);
">
  🏠 Apply for Pre-Approval
</button>

<!-- Modal overlay -->
<div id="buyer-intake-modal" style="
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.7);
  z-index: 9999;
  padding: 20px;
  overflow-y: auto;
">
  <div style="max-width: 1000px; margin: 0 auto; position: relative;">
    <button onclick="closeBuyerIntake()" style="
      position: absolute;
      right: 10px;
      top: 10px;
      background: white;
      border: none;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      font-size: 24px;
      cursor: pointer;
      box-shadow: 0 2px 10px rgba(0,0,0,0.2);
      z-index: 10000;
    ">×</button>

    <iframe
      src="https://mortgage-crm-nine.vercel.app/apply"
      width="100%"
      height="90vh"
      frameborder="0"
      style="border: none; border-radius: 12px; background: white;">
    </iframe>
  </div>
</div>

<script>
  function openBuyerIntake() {
    document.getElementById('buyer-intake-modal').style.display = 'block';
    document.body.style.overflow = 'hidden';
  }

  function closeBuyerIntake() {
    document.getElementById('buyer-intake-modal').style.display = 'none';
    document.body.style.overflow = 'auto';
  }

  // Close on background click
  document.getElementById('buyer-intake-modal').addEventListener('click', function(e) {
    if (e.target === this) {
      closeBuyerIntake();
    }
  });

  // Close on ESC key
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      closeBuyerIntake();
    }
  });
</script>
```

---

## 🔗 Alternative: Direct Link Options

### Option 5: Simple Text Link
```html
<a href="https://mortgage-crm-nine.vercel.app/apply"
   target="_blank"
   style="color: #217F8D; font-weight: 600; text-decoration: none;">
  Apply for Pre-Approval →
</a>
```

### Option 6: Styled Call-to-Action Button
```html
<a href="https://mortgage-crm-nine.vercel.app/apply"
   target="_blank"
   style="
     display: inline-block;
     padding: 14px 32px;
     background: linear-gradient(135deg, #217F8D 0%, #1a6670 100%);
     color: white;
     text-decoration: none;
     border-radius: 8px;
     font-size: 16px;
     font-weight: 600;
     box-shadow: 0 4px 12px rgba(33, 127, 141, 0.3);
     transition: transform 0.2s;
   "
   onmouseover="this.style.transform='translateY(-2px)'"
   onmouseout="this.style.transform='translateY(0)'">
  🏠 Start Your Application
</a>
```

### Option 7: QR Code

Generate a QR code for the URL:
```
https://mortgage-crm-nine.vercel.app/apply
```

**Free QR Code Generators:**
- https://www.qr-code-generator.com/
- https://qrcode.tec-it.com/
- Google: "QR code generator"

Use QR codes on:
- Business cards
- Flyers and brochures
- Yard signs
- Open house materials
- Email signatures

---

## 🎨 WordPress Integration

If you're using WordPress, add this to your page editor (HTML mode):

```html
[raw]
<div style="max-width: 1000px; margin: 40px auto; padding: 20px;">
  <iframe
    src="https://mortgage-crm-nine.vercel.app/apply"
    width="100%"
    height="1200px"
    frameborder="0"
    style="border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
  </iframe>
</div>
[/raw]
```

Or use a plugin like "iFrame" or "Advanced iFrame" and simply paste:
```
https://mortgage-crm-nine.vercel.app/apply
```

---

## 📱 Squarespace Integration

1. Add a **Code Block** to your page
2. Paste this code:

```html
<div style="width: 100%; max-width: 1000px; margin: 0 auto;">
  <iframe
    src="https://mortgage-crm-nine.vercel.app/apply"
    width="100%"
    height="1200px"
    frameborder="0"
    style="border: none; border-radius: 12px;">
  </iframe>
</div>
```

---

## 🎯 Wix Integration

1. Click the **+** button to add elements
2. Select **Embed** → **Custom Embeds** → **Embed a Widget**
3. Click **Enter Code**
4. Paste this:

```html
<iframe
  src="https://mortgage-crm-nine.vercel.app/apply"
  width="100%"
  height="1200px"
  frameborder="0"
  style="border: none;">
</iframe>
```

---

## 🌐 Webflow Integration

1. Drag an **Embed** element onto your page
2. Paste this code:

```html
<iframe
  src="https://mortgage-crm-nine.vercel.app/apply"
  width="100%"
  height="1200px"
  frameborder="0"
  style="border: none; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
</iframe>
```

---

## 🔧 Advanced Customization

### Custom Height
Adjust the `height` attribute based on your needs:
- Minimum: `800px`
- Recommended: `1200px`
- Mobile: `1400px`

### Hide Header (Coming Soon)
To hide the gradient header and show only the form, we can add a URL parameter:
```
https://mortgage-crm-nine.vercel.app/apply?embedded=true
```
(This feature needs to be implemented in the app)

### Custom Success Redirect
After submission, redirect users to a custom thank-you page:
```
https://mortgage-crm-nine.vercel.app/apply?redirect=https://yoursite.com/thank-you
```
(This feature needs to be implemented in the app)

---

## 📊 Tracking & Analytics

### Google Analytics Tracking
The buyer intake form automatically tracks in your CRM. To track in Google Analytics, add this to your website:

```html
<script>
  // Track when form is loaded
  window.addEventListener('message', function(e) {
    if (e.data === 'buyer-intake-loaded') {
      gtag('event', 'form_view', {
        'form_name': 'buyer_intake'
      });
    }
    if (e.data === 'buyer-intake-submitted') {
      gtag('event', 'form_submit', {
        'form_name': 'buyer_intake'
      });
    }
  });
</script>
```

---

## ✅ Testing Your Embed

After embedding, test:

1. ✅ Form loads correctly
2. ✅ All fields are visible and functional
3. ✅ Form is responsive on mobile devices
4. ✅ Submit button works
5. ✅ Success message appears after submission
6. ✅ Data appears in your CRM Leads page with "NEW" badge

**Test URL:** https://mortgage-crm-nine.vercel.app/apply

---

## 🚀 Quick Start

**Fastest way to embed:**

1. Copy this code:
```html
<iframe src="https://mortgage-crm-nine.vercel.app/apply" width="100%" height="1200px" frameborder="0"></iframe>
```

2. Paste it into your website's HTML editor

3. Done! ✅

---

## 📞 Support

If you have issues with embedding:
1. Ensure your website allows iframes
2. Check browser console for errors
3. Try different height values
4. Test on incognito/private browsing mode

The application is public and requires no authentication, so it should work on any website that allows iframes.
