# Litera Compare - Exhaustive Feature Research

> Research compiled April 2026. Litera Compare (formerly Workshare Compare / DeltaView) is used by 72% of the legal industry and 99% of Am Law 100 firms.

---

## 1. DOCUMENT COMPARISON FEATURES

### 1.1 Supported File Formats
- **Microsoft Word** (.doc, .docx) - primary format
- **PDF** (native text-based and scanned/image-based via OCR)
- **Excel** (.xls, .xlsx) - spreadsheet comparison
- **PowerPoint** (.ppt, .pptx) - presentation comparison
- **RTF** (Rich Text Format)
- **TXT** (Plain Text)
- **HTML**
- **Email bodies** (Outlook .msg)
- **Cross-format comparison** (e.g., Word vs PDF, Word vs RTF)

### 1.2 Comparison Modes
- **1:1 Comparison** - Compare two documents against each other
- **1:Many (One-to-Many) Comparison** - Compare up to 5 modified versions against a single original; merge accepted changes from multiple comparisons into a single clean copy
- **Bulk Comparison** - Compare multiple document pairs
- **Selective Compare** - Compare specific sections/paragraphs within a larger document via drag-and-drop of content snippets
- **Clipboard Compare (Compare Selections)** - Compare text on Windows clipboard with currently selected text
- **Email Thread Comparison** - Compare any two emails in a thread (not just consecutive replies) directly in Outlook
- **Compare by Email** - Email two documents to a configured server mailbox and receive a redline back via email (no UI needed)
- **Cross-format Comparison** - Compare a Word doc against a PDF, etc.

### 1.3 What Gets Compared (Change Detection)
- **Text changes** - additions, deletions, modifications
- **Table changes** - content within tables
- **Chart changes**
- **Image changes** - pixel-by-pixel comparison or ignore option
- **Shapes** (in PowerPoint)
- **Comments** - analyzed as comments (not converted to text)
- **Headers and footers** - including layout changes (e.g., first page header on/off)
- **Footnotes and endnotes** - with option to ignore footnote/endnote numbering while showing content changes
- **Numbering changes** - automatic/manual numbering detection
- **Formatting changes** - font size, font attributes, paragraph alignment, spacing, etc.
- **Hidden layout changes**
- **Embedded objects** - Excel spreadsheets, Visio diagrams, ChemDraw, SmartDraw
- **Embedded images** - JPG, TIFF, BMP, GIF, PNG, etc.
- **Moves/cuts** - text moved from one location to another
- **OCR for scanned PDFs** - automatic OCR applied to image-based PDFs

### 1.4 Compound Document Comparison (Patented)
- Patented technology for comparing "compound" documents
- Detects changes across the entire document structure: text, tables, images, shapes, headers/footers, footnotes, comments, embedded images, embedded objects
- Compares embedded Excel tables within Word documents
- XML-level comparison (not RTF-based) for accuracy and speed

---

## 2. RENDERING SETS / DISPLAY OPTIONS

### 2.1 Rendering Sets Manager
- Create, modify, and delete rendering sets
- Save multiple configurations of how redlines are represented
- Share rendering sets with clients who expect specific redline formats
- Corporate rendering sets vs. personal rendering sets
- Rendering sets control OCR options for PDF comparison

### 2.2 Comparison Styles
- Edit, create, delete, and rename comparison styles
- Corporate comparison styles (organization-wide)
- Personal comparison styles (per-user)
- Session-level option overrides (temporary changes to current comparison)

### 2.3 Markup Formatting
- **Deletions**: Red text with strikethrough (default)
- **Insertions/Additions**: Bright blue text with double underline (default)
- **Moved/Cut text**: Green text with strikethrough (default)
- **Pasted/Copied text**: Green text with double underline (default)
- **Configurable font effects**: Bold, Italic, Underline, Double-underline, Strikethrough, Double strikethrough
- **Configurable colors** per change type
- **Vertical change lines (change bars)**: Show for all changes, additions only, or deletions only; displayed in Document Viewer and saved in PDF output

### 2.4 Character-Level Comparison Options
- **OFF**: Marks entire words as changed if any character changes
- **ON**: Marks individual character changes with a predefined threshold
- **ON - Ignore Numbers**: Treats any digit change as changing the entire number
- **Enhanced mode**: Smoother readability markup for character comparison
- **Classic mode**: More granular markup emphasizing precision

### 2.5 Image Comparison Options
- Pixel-by-pixel comparison
- Option to not compare (ignore) embedded images

### 2.6 Space/Whitespace Options
- Show/hide space changes within paragraphs and sentences

---

## 3. CHANGE CATEGORIES & FILTERING

### 3.1 Change Types
- **Additions** - content in modified but not in original
- **Deletions** - content in original but not in modified
- **Moves** - content relocated within the document
- **Differences** - images or embedded objects that differ

### 3.2 Filter Options
- Filter by document location: Body, Headers, Footers, Comments, Tables
- Filter by content vs. format vs. layout
- Filter by change type and quantity
- Toggle formatting comparison on/off entirely (disable formatting changes)
- Option to ignore footnote/endnote numbering changes

---

## 4. ACCEPT/REJECT WORKFLOW

- Checkbox-based selection: check = accept, uncheck = reject
- Individual change accept/reject
- Batch accept/reject of changes
- Review changes by jumping from change to change
- For 1:Many comparisons: merge accepted changes from multiple redlines into a single new clean copy
- Create final document directly from accepted/rejected changes

---

## 5. UI FEATURES (PANELS, NAVIGATION, VIEWS)

### 5.1 Compare Tab Ribbon Groups (Word Add-in)
Four workflow groups: **Select**, **Compare**, **Review**, **Share**

### 5.2 Document Viewer / Three-Pane View
- Three synchronized scrolling windows: Original, Modified, Redline
- View any or all panes
- Synchronized scrolling across panes

### 5.3 Change List Panel
- Lists all detected changes with numbering
- Auto-minimizes after comparison to maximize redline viewing area
- Can be opened/closed as needed
- Click to navigate to specific changes
- Scroll or jump between changes
- Use numbered changes as reference points in discussions

### 5.4 Navigation
- Jump from change to change (next/previous)
- Scroll through changes
- Click changes in the Change List to navigate
- Changes Filter dropdown to filter the Change List

### 5.5 Redline Pages
- View only pages with changes (changes-only view)
- Print only pages with changes
- Email only pages with changes

---

## 6. OUTPUT / EXPORT OPTIONS

### 6.1 Save Formats
- Save redline as **Track Changes Word document** (.docx)
- Save as **DOCX**
- Save as **PDF**
- Save as **PDF/A**
- Interactive browser-based viewer
- Static redline document

### 6.2 Reports
- **Summary change report** - simple summary of changes, auto-appended
- **Detailed change report** - lists every change, auto-appended
- **Changes-only report** - document with only pages that have changes
- Change list / detailed change report attached with redline

### 6.3 Email/Share
- Email comparison documents directly from within Litera Compare
- Auto-create ZIP when multiple documents are sent
- Option to email only pages with changes
- Option to include source documents
- Email redline pages option

### 6.4 Print
- Print entire redline
- Print only pages with changes
- Print either source document

---

## 7. DMS INTEGRATIONS

### 7.1 Supported DMS Systems
- **iManage** (Work 10+) - deep integration with right-click context menu
- **NetDocuments**
- **Microsoft SharePoint** (via Universal File Picker in Litera One)
- **Microsoft OneDrive**
- **OpenText eDocs DM**
- **Worldox**
- **Epona**
- **Google Suite / G Suite**

### 7.2 DMS Integration Features
- Open/save documents directly from/to DMS
- Compare documents stored in DMS
- Right-click context menu in DMS (iManage, OpenText)
- Document name and document number options for DMS with doc IDs
- Compare versions of the same document within DMS
- Concurrent multi-DMS support (e.g., SharePoint + iManage + NetDocuments + OneDrive simultaneously)

### 7.3 Universal File Picker (Litera One Platform)
- Single interface to access documents across all connected DMS systems
- Browse and select documents from any connected repository
- Cross-repository document access

---

## 8. EMAIL INTEGRATION (OUTLOOK)

- **Outlook Add-in** - compare documents directly from Outlook
- **Email Thread Comparison** - compare any two emails in a thread to track language shifts in negotiations
- Not limited to consecutive replies - compare any email against any earlier message in the chain
- Works directly inside Outlook (no workflow change needed)
- Included in Base, Pro, and Advanced plans
- Single admin consent step activates for entire organization
- Compare attachments received via email
- Send comparison requests by email (Compare Server)

---

## 9. SECURITY & METADATA FEATURES

### 9.1 Integration with Litera Metadact
- Detect and clean 300+ types of metadata
- Clean Microsoft 365 documents, PDF, images, ZIP files
- Azure Information Protection (AIP) integration
- File encryption and label re-application after cleaning
- Server-side or desktop-side cleaning
- DLP (Data Loss Prevention) capabilities
- Alert email senders when replying all or forwarding with attachments
- Block suspicious emails
- Configurable metadata cleaning profiles

### 9.2 Clean and Compare Workflow
- Remove tracked changes before comparison
- Delete comments before comparison
- Strip metadata before sharing redlines
- Automatic cover page and table of contents insertion
- Password-protected attachments

---

## 10. COLLABORATION FEATURES

- Share redlines via email directly from the application
- One-to-Many comparison for multi-contributor review
- Merge changes from multiple reviewers into single document
- Numbered changes for discussion reference
- Change reports for stakeholder communication
- Cross-platform access (desktop, web, mobile) for distributed teams

---

## 11. AI FEATURES (LITO)

- **Lito** - AI Legal Agent integrated into Litera Compare
- Summarize changes between document versions
- Analyze risk of changes
- Evaluate mitigations
- Suggest clause rewrites
- Chat-based redlining
- Available in Outlook, Word, Web, and Apple iOS
- Dynamic grid interface for running multiple prompts across multiple documents
- Integrated document viewers for quick review of AI insights
- Included for all Litera Compare customers (no additional cost)

---

## 12. DEPLOYMENT OPTIONS & PLATFORMS

### 12.1 Product Editions
- **Litera Compare Desktop** - Windows desktop application with Office add-ins
- **Litera Compare Server** - Web service for server-side comparisons
- **Litera Compare for Microsoft 365 (Web Application)** - Browser-based in Word Online
- **Litera Compare for iOS** - Mobile access

### 12.2 Platform Support
- Windows (desktop)
- macOS (via server/web)
- iOS (iPhone/iPad)
- Android (via web browser)
- Any modern web browser

### 12.3 Deployment
- On-premise server deployment
- Cloud-hosted deployment
- Desktop installation with MSI/configuration files
- Configuration files stored at C:\ProgramData\Litera\DMS\Config\

### 12.4 Access Points for Initiating Comparison
- Microsoft Word ribbon/add-in
- Microsoft Outlook add-in
- Web browser (Litera One)
- DMS context menu (right-click in iManage, OpenText, etc.)
- Windows File Explorer right-click (Windows 11)
- Email-based (send docs to server mailbox)
- iOS app
- Desktop application standalone

---

## 13. API / AUTOMATION CAPABILITIES

### 13.1 Litera Compare Server API
- RESTful web service for server-side document comparison
- Exposes APIs for integration with client applications
- Supports Mac, PC, tablets, and other devices
- Developer portal at developer.workshare.net
- API documentation, interactive testing, API key management
- Rendering set configuration via API

### 13.2 Supported Formats via API
- Microsoft Word
- RTF
- PDF
- TXT
- HTML

### 13.3 Automation Features
- Compare by Email - automated comparison via mailbox
- Server-side batch processing
- Integration with third-party applications (LawVu, LexWorkplace, Recital, Sandline, etc.)
- DeltaView comparison engine technology

---

## 14. ADMINISTRATION & MANAGEMENT

### 14.1 Litera Administrator Panel (LAP)
- Centralized management console
- Configure functionality and appearance of Litera Compare
- Manage DMS and Office integration settings
- Save and distribute configuration files
- Role-based access controls
- Enterprise authentication support
- Granular permission settings
- Enforce consistent settings across organization
- Centralized policy management
- Standardized profiles for deployment
- Automated deployment options

### 14.2 Configuration Management
- Corporate vs. personal comparison styles
- DMS right-click menu configuration (none, all, Compare only, Metadact only)
- Group policy support
- Configuration file distribution

---

## 15. PRICING & PLANS

### 15.1 Plan Tiers
- **Base** - core comparison features
- **Pro** - additional capabilities
- **Advanced** - full feature set

### 15.2 Pricing
- Starts at ~$195/user/year (Base plan)
- One-year subscription (365 days)
- Auto-renewal
- Lito AI included at no additional cost for all plans
- Email thread comparison included in all plans

---

## 16. THIRD-PARTY INTEGRATIONS

- **LawVu** - track document changes
- **LexWorkplace** - inline document compare
- **Recital** - document comparison
- **Sandline** - document management
- **Microsoft 365** ecosystem (Word, Outlook, SharePoint, OneDrive, Teams)
- **Microsoft AppSource / Marketplace** listing
- Any application via Compare Server REST API

---

## 17. COMPETITIVE DIFFERENTIATORS (from marketing/reviews)

- Patented comparison algorithm with thorough testing
- XML-level comparison (not RTF-based like older tools)
- No missed changes or false positives (marketing claim)
- Compound document comparison (patented)
- Cross-format comparison (Word vs PDF)
- Built-in OCR for scanned PDFs
- Email thread comparison (unique feature)
- AI-powered risk analysis (Lito)
- 72% legal industry market share
- 99% Am Law 100 adoption
- 24/7 live support

---

## 18. KNOWN LIMITATIONS (from user reviews)

- Slow performance with large documents
- Sometimes incorrectly updates Table of Contents by adding unwanted heading levels
- Software bugs requiring extra support
- Poor search functionality for locating output files
- Customer support quality concerns
- Perceived as expensive, especially for smaller firms
- Layout/workflow complications in certain scenarios

---

## 19. PRODUCT HISTORY

- Originally **DeltaView** by WorkShare
- Rebranded to **WorkShare Compare / Workshare Professional**
- 2019: Litera acquired Workshare
- 2020: Litera acquired DocsCorp (compareDocs)
- Unified as **Litera Compare** under the Litera brand
- Now part of the **Litera One** integrated platform
- Compare Server retains "DeltaView" comparison engine technology

---

*Sources: Litera.com, Litera Support documentation, G2 reviews, Capterra reviews, GetApp, Scribd user guides, Litera product sheets, iManage partner documentation, LawVu/LexWorkplace integration docs, various legal technology publications.*
