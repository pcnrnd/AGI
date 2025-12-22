import pandas as pd
from pathlib import Path


class SandboxDataNormalizer:
    """
    샌드박스 데이터를 공통 스키마로 정규화하는 클래스
    
    다양한 샌드박스 타입(ICT, 규제자유특구, 금융, 산업융합 법령/사례)의 데이터를
    공통 컬럼 스키마로 변환하고 통합하는 기능을 제공합니다.
    """
    
    # 공통 컬럼 스키마
    COMMON_COLS = [
        "index",            # 행 인덱스(숫자)
        "sandbox_type",     # ICT / REG_ZONE / FIN / IND_LAW / IND_CASE
        "category",         # 구분/제도/분류
        "title",            # 사례명/서비스명/사업명/제목
        "main_content",     # 서비스 내용/현황/주요내용
        "regulatory_issue", # 규제 내용/현행 규제
        "regulatory_relief",# 특례·허용·규제개정현황
        "conditions",       # 부가조건/주요 부가 조건
        "expected_effect",  # 기대효과
        "achievements"      # 성과/개선결과
    ]
    
    def __init__(self, base_dir=".", encoding="utf-8-sig"):
        """
        SandboxDataNormalizer 초기화
        
        Args:
            base_dir (str or Path): 데이터 파일이 위치한 기본 디렉토리 경로
            encoding (str): CSV 저장 시 사용할 인코딩 (기본값: utf-8-sig)
        """
        self.base_dir = Path(base_dir)
        self.encoding = encoding
    
    def _read_source_file(self, filepath):
        """
        소스 파일을 읽어 DataFrame으로 반환 (CSV/Excel 자동 감지)
        
        Args:
            filepath (Path): 읽을 파일 경로
            
        Returns:
            pd.DataFrame: 읽어온 데이터프레임
            
        Raises:
            FileNotFoundError: 파일이 존재하지 않을 경우
            ValueError: 지원하지 않는 파일 형식일 경우
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {filepath}")
        
        suffix = filepath.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(filepath)
        elif suffix in [".xlsx", ".xls"]:
            return pd.read_excel(filepath)
        else:
            raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix}")
    
    def _ensure_common_columns(self, df):
        """
        DataFrame이 공통 컬럼을 모두 포함하도록 보장하고 순서를 맞춤
        
        Args:
            df (pd.DataFrame): 정규화할 DataFrame
            
        Returns:
            pd.DataFrame: 공통 컬럼 순서로 정렬된 DataFrame
        """
        # 누락된 컬럼을 빈 문자열로 추가
        for col in self.COMMON_COLS:
            if col not in df.columns:
                df[col] = ""
        
        # 공통 컬럼 순서로 재정렬
        return df[self.COMMON_COLS]
    
    def _save_normalized(self, df, output_filename):
        """
        정규화된 DataFrame을 CSV 파일로 저장
        
        Args:
            df (pd.DataFrame): 저장할 DataFrame
            output_filename (str): 출력 파일명
            
        Returns:
            Path: 저장된 파일 경로
        """
        output_path = self.base_dir / output_filename
        df.to_csv(output_path, index=False, encoding=self.encoding)
        return output_path
    
    def _create_index_column(self, df, index_col=None, start_from=1):
        """
        인덱스 컬럼 생성 (기존 컬럼이 없을 경우)
        
        Args:
            df (pd.DataFrame): 대상 DataFrame
            index_col (str, optional): 기존 인덱스 컬럼명
            start_from (int): 인덱스 시작 번호 (기본값: 1)
            
        Returns:
            pd.Series: 인덱스 컬럼 시리즈
        """
        if index_col and index_col in df.columns:
            return df[index_col]
        else:
            return pd.Series(range(start_from, len(df) + start_from))
    
    def normalize_ict(self):
        """
        ICT_규제_샌드박스.csv → 공통 스키마로 변환
        
        예상 원본 컬럼:
            - 번호, 구분, 서비스명, 서비스 내용, 규제, 특례 내용, 부가조건, 기대효과, 개선결과
            
        Returns:
            pd.DataFrame: 정규화된 DataFrame
        """
        src = self.base_dir / "ICT_규제_샌드박스.csv"
        df = self._read_source_file(src)
        
        mapping = {
            "번호": "index",
            "구분": "category",
            "서비스명": "title",
            "서비스 내용": "main_content",
            "규제": "regulatory_issue",
            "특례 내용": "regulatory_relief",
            "부가조건": "conditions",
            "기대효과": "expected_effect",
            "개선결과": "achievements",
        }
        
        # 필요한 컬럼만 선택 후 이름 변경
        df = df[list(mapping.keys())].rename(columns=mapping)
        df["sandbox_type"] = "ICT"
        
        # 공통 컬럼 순서 맞추기
        df = self._ensure_common_columns(df)
        self._save_normalized(df, "normalized_ICT_규제_샌드박스.csv")
        return df
    
    def normalize_regzone(self):
        """
        규제자유특구.csv → 공통 스키마로 변환
        
        예상 원본 컬럼(필요에 따라 이름 수정 가능):
            - 대제목, 중제목, 소제목, 현황, 허용
            * 규제 이슈는 '현황' 안에 서술되어 있을 수 있으므로 그대로 main_content와 함께 넣거나,
              별도 규제 설명 컬럼이 있으면 그걸 mapping에 지정.
            
        Returns:
            pd.DataFrame: 정규화된 DataFrame
        """
        src = self.base_dir / "규제자유특구.csv"
        df = self._read_source_file(src)
        
        # 행 인덱스가 따로 없다고 가정하고 1부터 부여
        df["index"] = self._create_index_column(df)
        
        # category를 대제목 / 중제목 결합으로 구성 (컬럼명이 다르면 아래를 수정)
        if {"대제목", "중제목"}.issubset(df.columns):
            df["category"] = df["대제목"].astype(str) + " / " + df["중제목"].astype(str)
        elif "대제목" in df.columns:
            df["category"] = df["대제목"]
        else:
            df["category"] = ""
        
        # 기본값 초기화
        out_df = pd.DataFrame()
        out_df["index"] = df["index"]
        out_df["sandbox_type"] = "REG_ZONE"
        out_df["category"] = df.get("category", "")
        out_df["title"] = df.get("소제목", "")
        out_df["main_content"] = df.get("현황", "")
        # 규제 이슈가 따로 없으면 main_content에서 요약된다고 보고 비워둔다.
        out_df["regulatory_issue"] = df.get("규제내용", "")
        out_df["regulatory_relief"] = df.get("허용", "")
        out_df["conditions"] = ""          # (없음)
        out_df["expected_effect"] = ""     # (없음)
        out_df["achievements"] = ""        # (없음)
        
        out_df = self._ensure_common_columns(out_df)
        self._save_normalized(out_df, "normalized_규제자유특구.csv")
        return out_df
    
    def normalize_fin(self):
        """
        금융_샌드박스_사례.csv → 공통 스키마로 변환
        
        예상 원본 컬럼:
            - 지정 제도, 서비스명, 서비스 주요 내용, (규제내용/본문 일부), 규제 특례 내용, 주요 부가 조건 내용
            
        Returns:
            pd.DataFrame: 정규화된 DataFrame
        """
        src = self.base_dir / "금융_샌드박스_사례.csv"
        df = self._read_source_file(src)
        
        df["index"] = self._create_index_column(df)
        
        out_df = pd.DataFrame()
        out_df["index"] = df["index"]
        out_df["sandbox_type"] = "FIN"
        out_df["category"] = df.get("지정 제도", "")
        out_df["title"] = df.get("서비스명", "")
        out_df["main_content"] = df.get("서비스 주요 내용", "")
        # 규제 이슈가 '규제내용' 또는 '본문 일부' 같은 이름일 수 있으므로 우선순위로 가져오기
        if "규제내용" in df.columns:
            out_df["regulatory_issue"] = df["규제내용"]
        elif "본문 일부" in df.columns:
            out_df["regulatory_issue"] = df["본문 일부"]
        else:
            out_df["regulatory_issue"] = ""
        out_df["regulatory_relief"] = df.get("규제 특례 내용", "")
        out_df["conditions"] = df.get("주요 부가 조건 내용", "")
        out_df["expected_effect"] = ""
        out_df["achievements"] = ""
        
        out_df = self._ensure_common_columns(out_df)
        self._save_normalized(out_df, "normalized_금융_샌드박스_사례.csv")
        return out_df
    
    def normalize_ind_law(self):
        """
        산업융합_샌드박스_법령.csv → 공통 스키마로 변환
        
        예상 원본 컬럼:
            - 순번, 국조실분류, 사업명, 규제내용
            
        Returns:
            pd.DataFrame: 정규화된 DataFrame
        """
        src = self.base_dir / "산업융합_샌드박스_법령.csv"
        df = self._read_source_file(src)
        
        out_df = pd.DataFrame()
        out_df["index"] = self._create_index_column(df, index_col="순번")
        out_df["sandbox_type"] = "IND_LAW"
        out_df["category"] = df.get("국조실분류", "")
        out_df["title"] = df.get("사업명", "")
        # 규제내용 일부를 main_content로도 활용
        out_df["main_content"] = df.get("규제내용", "")
        out_df["regulatory_issue"] = df.get("규제내용", "")
        out_df["regulatory_relief"] = ""
        out_df["conditions"] = ""
        out_df["expected_effect"] = ""
        out_df["achievements"] = ""
        
        out_df = self._ensure_common_columns(out_df)
        self._save_normalized(out_df, "normalized_산업융합_샌드박스_법령.csv")
        return out_df
    
    def normalize_ind_case(self):
        """
        산업융합_샌드박스_사례_124_20251024.xlsx → 공통 스키마로 변환
        
        예상 원본 컬럼:
            - 번호, 구분(Category), 제목, 주요내용, 규제내용, 규제개정현황(유사), 기대효과, 주요성과
            
        Returns:
            pd.DataFrame: 정규화된 DataFrame
        """
        src = self.base_dir / "산업융합_샌드박스_사례_124_20251024.xlsx"
        df = self._read_source_file(src)
        
        out_df = pd.DataFrame()
        out_df["index"] = self._create_index_column(df, index_col="번호")
        out_df["sandbox_type"] = "IND_CASE"
        # 구분(Category) 라는 이름일 가능성 높음
        if "구분(Category)" in df.columns:
            out_df["category"] = df["구분(Category)"]
        elif "구분" in df.columns:
            out_df["category"] = df["구분"]
        else:
            out_df["category"] = ""
        out_df["title"] = df.get("제목", "")
        out_df["main_content"] = df.get("주요내용", "")
        out_df["regulatory_issue"] = df.get("규제내용", "")
        out_df["regulatory_relief"] = df.get("규제개정현황(유사)", "")
        out_df["conditions"] = ""
        out_df["expected_effect"] = df.get("기대효과", "")
        out_df["achievements"] = df.get("주요성과", "")
        
        out_df = self._ensure_common_columns(out_df)
        self._save_normalized(out_df, "normalized_산업융합_샌드박스_사례.csv")
        return out_df
    
    def normalize_all(self):
        """
        모든 샌드박스 타입의 데이터를 정규화
        
        Returns:
            list[pd.DataFrame]: 정규화된 모든 DataFrame 리스트
        """
        dfs = []
        dfs.append(self.normalize_ict())
        dfs.append(self.normalize_regzone())
        dfs.append(self.normalize_fin())
        dfs.append(self.normalize_ind_law())
        dfs.append(self.normalize_ind_case())
        return dfs
    
    def merge_all(self, output_filename="sandbox_master_normalized.csv"):
        """
        모든 정규화된 데이터를 통합하여 마스터 파일 생성
        
        Args:
            output_filename (str): 출력 마스터 파일명 (기본값: sandbox_master_normalized.csv)
            
        Returns:
            pd.DataFrame: 통합된 마스터 DataFrame
        """
        dfs = self.normalize_all()
        master = pd.concat(dfs, ignore_index=True)
        output_path = self._save_normalized(master, output_filename)
        print(f"통합 마스터 CSV 저장 완료: {output_path}")
        return master


def main():
    """
    메인 실행 함수 (기존 호환성 유지)
    """
    normalizer = SandboxDataNormalizer()
    normalizer.merge_all()


if __name__ == "__main__":
    main()
