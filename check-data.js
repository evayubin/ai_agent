import { Client } from "@notionhq/client";
import dotenv from "dotenv";
import fs from "fs";

dotenv.config();

const notion = new Client({ auth: process.env.NOTION_API_KEY });
const databaseId = process.env.NOTION_DATABASE_ID;
const LOCAL_FILE = "crawl_result.json";

async function doubleCheck() {
  console.log("🐌 [로즈]: 장부를 대조해 볼 테니 잠시만요!!");

  // 1. 로컬 파일 확인
  if (fs.existsSync(LOCAL_FILE)) {
    const localData = JSON.parse(fs.readFileSync(LOCAL_FILE, "utf-8"));
    console.log(`\n📂 [로컬 파일]: '${LOCAL_FILE}' 발견!`);
    console.log(`   - 설리가 가방에 넣어둔 공고: ${localData.length}개`);
  } else {
    console.log(`\n❌ [로컬 파일]: '${LOCAL_FILE}'을 찾을 수 없군. 설리가 땡땡이친 건가?`);
  }

  // 2. 노션 DB 확인
  try {
    const response = await notion.databases.query({
        database_id: databaseId,
        page_size: 100 // 최근 100개까지 확인
    });
    
    console.log(`\n📊 [노션 DB]: '${databaseId}' 연결됨.`);
    console.log(`   - 현재 장부에 기록된 총 공고: ${response.results.length}개`);

    if (response.results.length > 0) {
        console.log(`   - 가장 최근 등록된 공고: ${response.results[0].properties.Title?.title[0]?.plain_text || "제목 없음"}`);
        console.log("\n✅ [로즈]: 장부 기록까지 완벽하군. 확인해 보게나.");
    } else {
        console.log("\n⚠️ [로즈]: 파일은 있는데 노션 장부는 비어 있네. 설리한테 전송하라고 소리 좀 쳐야겠어.");
    }
  } catch (error) {
    console.log("\n❌ [로즈]: 노션 API 연결 실패. 내 돋보기가 고장 났거나 키값이 틀렸군.");
  }
}

doubleCheck();