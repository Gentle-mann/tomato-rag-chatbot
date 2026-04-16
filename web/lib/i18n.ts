import { useChatStore } from './store'

type Language = 'en' | 'ne' | 'ja' | 'id' | 'vi'

const translations: Record<Language, Record<string, string>> = {
  en: {
    // app/page.tsx
    'app.title': 'Tomato Cultivation Assistant',
    'app.admin': 'Admin',
    'app.footer1': 'Answers are based solely on the provided reference materials.',
    'app.footer2': 'Always verify critical information with local agricultural experts.',

    // WelcomeScreen.tsx
    'welcome.title': 'Tomato Cultivation Assistant',
    'welcome.description':
      'Ask me anything about growing tomatoes! I provide answers based on the cultivation manual and video transcript, with citations for every response.',
    'welcome.note':
      "Note: I can only answer questions covered in the tomato cultivation manual or video transcript. If the information isn't in these sources, I'll let you know.",
    'welcome.cat.seedling': 'Seedling Care',
    'welcome.cat.irrigation': 'Irrigation',
    'welcome.cat.disease': 'Disease Control',
    'welcome.cat.environment': 'Environment',
    'welcome.q.seedling': 'How do I start tomato seedlings?',
    'welcome.q.irrigation': 'What is the best watering schedule for tomatoes?',
    'welcome.q.disease': 'How do I prevent common tomato diseases?',
    'welcome.q.environment': 'What temperature is ideal for tomato growth?',

    // ChatInterface.tsx
    'chat.error': 'Sorry, I encountered an error. Please try again.',
    'chat.stream': 'Stream responses',
    'chat.session': 'Session',
    'chat.sessionNew': 'New',

    // ChatInput.tsx
    'input.placeholder': 'Ask about tomato cultivation...',
    'input.listening': 'Listening... speak now',
    'input.voiceStart': 'Start voice input',
    'input.voiceStop': 'Stop recording',

    // ChatMessage.tsx
    'message.source': 'source',
    'message.sources': 'sources',

    // CitationCard.tsx
    'citation.page': 'Page',
    'citation.match': 'match',
    'citation.manual': 'Manual',
    'citation.transcript': 'Video',
    'citation.timestamp': 'Timestamp',

    // Feedback
    'feedback.helpful': 'Helpful',
    'feedback.unhelpful': 'Not helpful',

    // Region selector
    'region.auto': 'Auto-detect',
    'region.japan': 'Japan',
    'region.nepal': 'Nepal',
    'region.vietnam': 'Vietnam',
    'region.indonesia': 'Indonesia',
    'region.philippines': 'Philippines',

    // Admin documents page
    'admin.back': 'Back to Chat',
    'admin.title': 'Document Management',
    'admin.subtitle': 'Upload and manage PDF documents for the RAG chatbot',
    'admin.upload': 'Upload PDF',
    'admin.uploading': 'Uploading...',
    'admin.pdfOnly': 'Only PDF files are supported',
    'admin.uploadFailed': 'Failed to upload document',
    'admin.deleteFailed': 'Failed to delete document',
    'admin.reprocessFailed': 'Failed to reprocess document',
    'admin.deleteConfirm': 'Are you sure you want to delete this document?',
    'admin.empty': 'No documents uploaded yet. Upload a PDF to get started.',
    'admin.colStatus': 'Status',
    'admin.colFilename': 'Filename',
    'admin.colPages': 'Pages',
    'admin.colChunks': 'Chunks',
    'admin.colUploaded': 'Uploaded',
    'admin.colActions': 'Actions',
  },

  ja: {
    'app.title': 'トマト栽培アシスタント',
    'app.admin': '管理',
    'app.footer1': '回答は提供された参考資料のみに基づいています。',
    'app.footer2': '重要な情報は必ず地域の農業専門家にご確認ください。',

    'welcome.title': 'トマト栽培アシスタント',
    'welcome.description':
      'トマト栽培について何でもお聞きください！栽培マニュアルと動画解説に基づき、引用付きで回答します。',
    'welcome.note':
      '注意：トマト栽培マニュアルまたは動画解説に記載されている質問のみお答えできます。資料に情報がない場合はお知らせします。',
    'welcome.cat.seedling': '育苗',
    'welcome.cat.irrigation': '灌水',
    'welcome.cat.disease': '病害防除',
    'welcome.cat.environment': '環境管理',
    'welcome.q.seedling': 'トマトの苗はどう育てますか？',
    'welcome.q.irrigation': 'トマトの水やりのスケジュールは？',
    'welcome.q.disease': 'トマトの病気を防ぐには？',
    'welcome.q.environment': 'トマトの成長に最適な温度は？',

    'chat.error': 'エラーが発生しました。もう一度お試しください。',
    'chat.stream': 'ストリーミング応答',
    'chat.session': 'セッション',
    'chat.sessionNew': '新規',

    'input.placeholder': 'トマト栽培について質問...',
    'input.listening': '聞いています...話してください',
    'input.voiceStart': '音声入力を開始',
    'input.voiceStop': '録音を停止',

    'message.source': '引用元',
    'message.sources': '引用元',

    'citation.page': 'ページ',
    'citation.match': '一致',
    'citation.manual': 'マニュアル',
    'citation.transcript': '動画',
    'citation.timestamp': 'タイムスタンプ',

    'feedback.helpful': '役に立った',
    'feedback.unhelpful': '役に立たなかった',

    'region.auto': '自動検出',
    'region.japan': '日本',
    'region.nepal': 'ネパール',
    'region.vietnam': 'ベトナム',
    'region.indonesia': 'インドネシア',
    'region.philippines': 'フィリピン',

    'admin.back': 'チャットに戻る',
    'admin.title': 'ドキュメント管理',
    'admin.subtitle': 'RAGチャットボット用のPDFドキュメントをアップロード・管理',
    'admin.upload': 'PDFアップロード',
    'admin.uploading': 'アップロード中...',
    'admin.pdfOnly': 'PDFファイルのみ対応しています',
    'admin.uploadFailed': 'ドキュメントのアップロードに失敗しました',
    'admin.deleteFailed': 'ドキュメントの削除に失敗しました',
    'admin.reprocessFailed': 'ドキュメントの再処理に失敗しました',
    'admin.deleteConfirm': 'このドキュメントを削除してもよろしいですか？',
    'admin.empty': 'ドキュメントがまだありません。PDFをアップロードしてください。',
    'admin.colStatus': 'ステータス',
    'admin.colFilename': 'ファイル名',
    'admin.colPages': 'ページ数',
    'admin.colChunks': 'チャンク数',
    'admin.colUploaded': 'アップロード日',
    'admin.colActions': '操作',
  },

  ne: {
    'app.title': 'टमाटर खेती सहायक',
    'app.admin': 'प्रशासन',
    'app.footer1': 'जवाफहरू प्रदान गरिएका सन्दर्भ सामग्रीमा मात्र आधारित छन्।',
    'app.footer2':
      'महत्त्वपूर्ण जानकारी सधैं स्थानीय कृषि विज्ञसँग पुष्टि गर्नुहोस्।',

    'welcome.title': 'टमाटर खेती सहायक',
    'welcome.description':
      'टमाटर उब्जाउने बारेमा जे पनि सोध्नुहोस्! म खेती पुस्तिका र भिडियो व्याख्याको आधारमा उद्धरणसहित जवाफ दिन्छु।',
    'welcome.note':
      'नोट: म टमाटर खेती पुस्तिका वा भिडियो व्याख्यामा भएका प्रश्नहरूको मात्र जवाफ दिन सक्छु। यी स्रोतहरूमा जानकारी नभएमा म तपाईंलाई जानकारी दिनेछु।',
    'welcome.cat.seedling': 'बिरुवा हेरचाह',
    'welcome.cat.irrigation': 'सिँचाइ',
    'welcome.cat.disease': 'रोग नियन्त्रण',
    'welcome.cat.environment': 'वातावरण',
    'welcome.q.seedling': 'टमाटरको बिरुवा कसरी सुरु गर्ने?',
    'welcome.q.irrigation': 'टमाटरको लागि उत्तम सिँचाइ तालिका के हो?',
    'welcome.q.disease': 'टमाटरका सामान्य रोगहरू कसरी रोक्ने?',
    'welcome.q.environment': 'टमाटर बढ्नको लागि उपयुक्त तापक्रम कति हो?',

    'chat.error': 'माफ गर्नुहोस्, त्रुटि भयो। कृपया फेरि प्रयास गर्नुहोस्।',
    'chat.stream': 'स्ट्रिम प्रतिक्रिया',
    'chat.session': 'सत्र',
    'chat.sessionNew': 'नयाँ',

    'input.placeholder': 'टमाटर खेतीबारे सोध्नुहोस्...',
    'input.listening': 'सुन्दै... अब बोल्नुहोस्',
    'input.voiceStart': 'आवाज इनपुट सुरु गर्नुहोस्',
    'input.voiceStop': 'रेकर्डिङ रोक्नुहोस्',

    'message.source': 'स्रोत',
    'message.sources': 'स्रोतहरू',

    'citation.page': 'पृष्ठ',
    'citation.match': 'मिल्दो',
    'citation.manual': 'पुस्तिका',
    'citation.transcript': 'भिडियो',
    'citation.timestamp': 'समय',

    'feedback.helpful': 'उपयोगी',
    'feedback.unhelpful': 'उपयोगी छैन',

    'region.auto': 'स्वचालित',
    'region.japan': 'जापान',
    'region.nepal': 'नेपाल',
    'region.vietnam': 'भिएतनाम',
    'region.indonesia': 'इन्डोनेसिया',
    'region.philippines': 'फिलिपिन्स',

    'admin.back': 'च्याटमा फर्कनुहोस्',
    'admin.title': 'कागजात व्यवस्थापन',
    'admin.subtitle': 'RAG च्याटबटको लागि PDF कागजातहरू अपलोड र व्यवस्थापन गर्नुहोस्',
    'admin.upload': 'PDF अपलोड',
    'admin.uploading': 'अपलोड हुँदैछ...',
    'admin.pdfOnly': 'PDF फाइलहरू मात्र समर्थित छन्',
    'admin.uploadFailed': 'कागजात अपलोड गर्न असफल',
    'admin.deleteFailed': 'कागजात मेटाउन असफल',
    'admin.reprocessFailed': 'कागजात पुन: प्रशोधन गर्न असफल',
    'admin.deleteConfirm': 'के तपाईं यो कागजात मेटाउन निश्चित हुनुहुन्छ?',
    'admin.empty': 'अहिलेसम्म कुनै कागजात अपलोड गरिएको छैन। सुरु गर्न PDF अपलोड गर्नुहोस्।',
    'admin.colStatus': 'स्थिति',
    'admin.colFilename': 'फाइल नाम',
    'admin.colPages': 'पृष्ठहरू',
    'admin.colChunks': 'खण्डहरू',
    'admin.colUploaded': 'अपलोड मिति',
    'admin.colActions': 'कार्यहरू',
  },

  id: {
    'app.title': 'Asisten Budidaya Tomat',
    'app.admin': 'Admin',
    'app.footer1': 'Jawaban hanya berdasarkan materi referensi yang tersedia.',
    'app.footer2': 'Selalu verifikasi informasi penting dengan ahli pertanian setempat.',

    'welcome.title': 'Asisten Budidaya Tomat',
    'welcome.description':
      'Tanyakan apa saja tentang menanam tomat! Saya memberikan jawaban berdasarkan manual budidaya dan transkrip video, dengan kutipan untuk setiap jawaban.',
    'welcome.note':
      'Catatan: Saya hanya dapat menjawab pertanyaan yang tercakup dalam manual budidaya tomat atau transkrip video. Jika informasi tidak tersedia, saya akan memberitahu Anda.',
    'welcome.cat.seedling': 'Perawatan Bibit',
    'welcome.cat.irrigation': 'Irigasi',
    'welcome.cat.disease': 'Pengendalian Penyakit',
    'welcome.cat.environment': 'Lingkungan',
    'welcome.q.seedling': 'Bagaimana cara memulai bibit tomat?',
    'welcome.q.irrigation': 'Apa jadwal penyiraman terbaik untuk tomat?',
    'welcome.q.disease': 'Bagaimana cara mencegah penyakit tomat yang umum?',
    'welcome.q.environment': 'Berapa suhu ideal untuk pertumbuhan tomat?',

    'chat.error': 'Maaf, terjadi kesalahan. Silakan coba lagi.',
    'chat.stream': 'Respons streaming',
    'chat.session': 'Sesi',
    'chat.sessionNew': 'Baru',

    'input.placeholder': 'Tanyakan tentang budidaya tomat...',
    'input.listening': 'Mendengarkan... silakan bicara',
    'input.voiceStart': 'Mulai input suara',
    'input.voiceStop': 'Hentikan perekaman',

    'message.source': 'sumber',
    'message.sources': 'sumber',

    'citation.page': 'Halaman',
    'citation.match': 'kecocokan',
    'citation.manual': 'Manual',
    'citation.transcript': 'Video',
    'citation.timestamp': 'Waktu',

    'feedback.helpful': 'Membantu',
    'feedback.unhelpful': 'Tidak membantu',

    'region.auto': 'Otomatis',
    'region.japan': 'Jepang',
    'region.nepal': 'Nepal',
    'region.vietnam': 'Vietnam',
    'region.indonesia': 'Indonesia',
    'region.philippines': 'Filipina',

    'admin.back': 'Kembali ke Chat',
    'admin.title': 'Manajemen Dokumen',
    'admin.subtitle': 'Unggah dan kelola dokumen PDF untuk chatbot RAG',
    'admin.upload': 'Unggah PDF',
    'admin.uploading': 'Mengunggah...',
    'admin.pdfOnly': 'Hanya file PDF yang didukung',
    'admin.uploadFailed': 'Gagal mengunggah dokumen',
    'admin.deleteFailed': 'Gagal menghapus dokumen',
    'admin.reprocessFailed': 'Gagal memproses ulang dokumen',
    'admin.deleteConfirm': 'Apakah Anda yakin ingin menghapus dokumen ini?',
    'admin.empty': 'Belum ada dokumen yang diunggah. Unggah PDF untuk memulai.',
    'admin.colStatus': 'Status',
    'admin.colFilename': 'Nama File',
    'admin.colPages': 'Halaman',
    'admin.colChunks': 'Potongan',
    'admin.colUploaded': 'Diunggah',
    'admin.colActions': 'Tindakan',
  },

  vi: {
    'app.title': 'Trợ lý Trồng Cà chua',
    'app.admin': 'Quản trị',
    'app.footer1': 'Câu trả lời chỉ dựa trên tài liệu tham khảo được cung cấp.',
    'app.footer2': 'Luôn xác minh thông tin quan trọng với chuyên gia nông nghiệp địa phương.',

    'welcome.title': 'Trợ lý Trồng Cà chua',
    'welcome.description':
      'Hãy hỏi bất cứ điều gì về trồng cà chua! Tôi cung cấp câu trả lời dựa trên sổ tay canh tác và bản ghi video, kèm trích dẫn cho mỗi câu trả lời.',
    'welcome.note':
      'Lưu ý: Tôi chỉ có thể trả lời các câu hỏi có trong sổ tay canh tác cà chua hoặc bản ghi video. Nếu thông tin không có trong các nguồn này, tôi sẽ cho bạn biết.',
    'welcome.cat.seedling': 'Chăm sóc cây con',
    'welcome.cat.irrigation': 'Tưới tiêu',
    'welcome.cat.disease': 'Kiểm soát bệnh',
    'welcome.cat.environment': 'Môi trường',
    'welcome.q.seedling': 'Làm thế nào để bắt đầu ươm cây cà chua?',
    'welcome.q.irrigation': 'Lịch tưới nước tốt nhất cho cà chua là gì?',
    'welcome.q.disease': 'Làm thế nào để phòng ngừa các bệnh thường gặp ở cà chua?',
    'welcome.q.environment': 'Nhiệt độ lý tưởng cho cà chua phát triển là bao nhiêu?',

    'chat.error': 'Xin lỗi, đã xảy ra lỗi. Vui lòng thử lại.',
    'chat.stream': 'Phản hồi trực tuyến',
    'chat.session': 'Phiên',
    'chat.sessionNew': 'Mới',

    'input.placeholder': 'Hỏi về trồng cà chua...',
    'input.listening': 'Đang lắng nghe... hãy nói',
    'input.voiceStart': 'Bắt đầu nhập bằng giọng nói',
    'input.voiceStop': 'Dừng ghi âm',

    'message.source': 'nguồn',
    'message.sources': 'nguồn',

    'citation.page': 'Trang',
    'citation.match': 'khớp',
    'citation.manual': 'Sổ tay',
    'citation.transcript': 'Video',
    'citation.timestamp': 'Thời gian',

    'feedback.helpful': 'Hữu ích',
    'feedback.unhelpful': 'Không hữu ích',

    'region.auto': 'Tự động',
    'region.japan': 'Nhật Bản',
    'region.nepal': 'Nepal',
    'region.vietnam': 'Việt Nam',
    'region.indonesia': 'Indonesia',
    'region.philippines': 'Philippines',

    'admin.back': 'Quay lại Chat',
    'admin.title': 'Quản lý Tài liệu',
    'admin.subtitle': 'Tải lên và quản lý tài liệu PDF cho chatbot RAG',
    'admin.upload': 'Tải PDF lên',
    'admin.uploading': 'Đang tải lên...',
    'admin.pdfOnly': 'Chỉ hỗ trợ file PDF',
    'admin.uploadFailed': 'Tải tài liệu lên thất bại',
    'admin.deleteFailed': 'Xóa tài liệu thất bại',
    'admin.reprocessFailed': 'Xử lý lại tài liệu thất bại',
    'admin.deleteConfirm': 'Bạn có chắc chắn muốn xóa tài liệu này không?',
    'admin.empty': 'Chưa có tài liệu nào được tải lên. Tải PDF lên để bắt đầu.',
    'admin.colStatus': 'Trạng thái',
    'admin.colFilename': 'Tên file',
    'admin.colPages': 'Trang',
    'admin.colChunks': 'Đoạn',
    'admin.colUploaded': 'Ngày tải',
    'admin.colActions': 'Thao tác',
  },
}

export function useTranslation() {
  const language = useChatStore((state) => state.language)
  const t = translations[language]
  return { t, language }
}
