import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./pages/Dashboard/PdfTranslator";
import OcrTest from "./pages/OcrTest/OcrTest";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/ocr-test" element={<OcrTest />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
