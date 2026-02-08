"""
Email Signature HTML Generator

Extracted from inline_legacy_routes.py for reuse across modules.
"""


def generate_email_signature_html(sig) -> str:
    """Generate HTML email signature matching the CMG template style"""
    phones = []
    if sig.office_phone:
        phones.append(f'<span style="color: #333;">&#9742; {sig.office_phone}</span>')
    if sig.cell_phone:
        phones.append(f'<span style="color: #333;">&#9990; {sig.cell_phone}</span>')
    if sig.fax:
        phones.append(f'<span style="color: #333;">&#128224; {sig.fax}</span>')
    phone_html = ' | '.join(phones) if phones else ''

    links = []
    if sig.apply_now_url:
        links.append(f'<a href="{sig.apply_now_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">APPLY NOW</a>')
    if sig.website_url:
        links.append(f'<a href="{sig.website_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">MYSITE</a>')
    if sig.doc_upload_url:
        links.append(f'<a href="{sig.doc_upload_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">DOC UPLOAD</a>')
    if sig.schedule_url:
        links.append(f'<a href="{sig.schedule_url}" style="color: {sig.primary_color}; text-decoration: none; font-weight: bold;">SCHEDULE</a>')
    links_html = ' | '.join(links) if links else ''

    social_icons = []
    if sig.linkedin_url:
        social_icons.append(f'<a href="{sig.linkedin_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/174/174857.png" alt="LinkedIn" width="20" height="20"></a>')
    if sig.facebook_url:
        social_icons.append(f'<a href="{sig.facebook_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/733/733547.png" alt="Facebook" width="20" height="20"></a>')
    if sig.instagram_url:
        social_icons.append(f'<a href="{sig.instagram_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/2111/2111463.png" alt="Instagram" width="20" height="20"></a>')
    if sig.twitter_url:
        social_icons.append(f'<a href="{sig.twitter_url}" style="margin: 0 4px;"><img src="https://cdn-icons-png.flaticon.com/24/733/733579.png" alt="Twitter" width="20" height="20"></a>')
    social_html = ''.join(social_icons) if social_icons else ''

    nmls_parts = []
    if sig.nmls_id:
        nmls_parts.append(f'NMLS# {sig.nmls_id}')
    if sig.branch_nmls_id:
        nmls_parts.append(f'BRANCH NMLS# {sig.branch_nmls_id}')
    if sig.corporate_nmls_id:
        nmls_parts.append(f'CORPORATE NMLS# {sig.corporate_nmls_id}')
    nmls_html = ' | '.join(nmls_parts) if nmls_parts else ''

    headshot_html = ''
    if sig.headshot_url:
        headshot_html = f'<td style="vertical-align: top; padding-right: 15px;"><img src="{sig.headshot_url}" alt="{sig.full_name or "Photo"}" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid {sig.primary_color};"></td>'

    logo_html = ''
    if sig.company_logo_url:
        tagline_span = f'<span style="background: {sig.secondary_color}; color: white; padding: 5px 15px; font-size: 11px; font-weight: bold; margin-left: 10px;">{sig.tagline}</span>' if sig.tagline else ''
        logo_html = f'<tr><td colspan="2" style="padding-top: 10px;"><img src="{sig.company_logo_url}" alt="Company Logo" style="max-height: 50px; max-width: 200px;">{tagline_span}</td></tr>'

    html = f'''<table cellpadding="0" cellspacing="0" border="0" style="font-family: Arial, sans-serif; font-size: 13px; color: #333; max-width: 500px;">
        <tr>
            {headshot_html}
            <td style="vertical-align: top;">
                <table cellpadding="0" cellspacing="0" border="0">
                    <tr><td style="font-size: 18px; font-weight: bold; color: {sig.primary_color};">{sig.full_name or ''}</td></tr>
                    {f'<tr><td style="font-size: 13px; color: #666;">{sig.team_name}</td></tr>' if sig.team_name else ''}
                    {f'<tr><td style="font-size: 13px; color: #666;">{sig.title}</td></tr>' if sig.title else ''}
                    <tr><td style="height: 8px;"></td></tr>
                    {f'<tr><td><a href="mailto:{sig.email}" style="color: {sig.primary_color}; text-decoration: none;">&#9993; {sig.email}</a></td></tr>' if sig.email else ''}
                    {f'<tr><td>{phone_html}</td></tr>' if phone_html else ''}
                    {f'<tr><td style="padding-top: 5px;">&#128205; {sig.address}</td></tr>' if sig.address else ''}
                    <tr><td style="height: 10px;"></td></tr>
                    {f'<tr><td>{links_html}</td></tr>' if links_html else ''}
                    {f'<tr><td style="padding-top: 8px;">{social_html}</td></tr>' if social_html else ''}
                    <tr><td style="height: 10px;"></td></tr>
                    {f'<tr><td style="font-size: 10px; color: #888;">{nmls_html}</td></tr>' if nmls_html else ''}
                </table>
            </td>
        </tr>
        {logo_html}
    </table>'''
    return html
