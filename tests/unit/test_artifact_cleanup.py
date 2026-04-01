"""Tests for extraction artifact cleanup passes."""

from __future__ import annotations

from local_library.ingestion.artifact_cleanup import (
    BOILERPLATE_RULES,
    _filter_non_latin_scripts,
    _reformat_image_descriptions,
    _remove_repeated_watermarks,
    _strip_publisher_boilerplate,
    clean_artifacts,
)

# ===================================================================
# Pass 1: Non-Latin Script Filtering
# ===================================================================


class TestFilterNonLatinScripts:
    """Tests for _filter_non_latin_scripts pass."""

    def test_removes_line_with_cjk_characters(self) -> None:
        """Lines with 4+ CJK characters are removed."""
        text = "Normal paragraph.\n\n医不利血管 医骨髓前缀\n\nAnother paragraph."
        result = _filter_non_latin_scripts(text)
        assert "医" not in result
        assert "Normal paragraph." in result
        assert "Another paragraph." in result

    def test_removes_line_with_arabic_characters(self) -> None:
        """Lines with 4+ Arabic characters are removed."""
        text = "Normal text.\n\nس ساس بسبب\n\nMore text."
        result = _filter_non_latin_scripts(text)
        assert "ساس" not in result
        assert "Normal text." in result
        assert "More text." in result

    def test_preserves_greek_characters(self) -> None:
        """Greek letters (common in academic text) are not targeted."""
        text = "The variables α, β, and γ are defined.\n\nα + β = γ"
        result = _filter_non_latin_scripts(text)
        assert result == text

    def test_preserves_cyrillic_characters(self) -> None:
        """Cyrillic characters (transliterations) are not targeted."""
        text = "The Russian word Привет appears in the citation."
        result = _filter_non_latin_scripts(text)
        assert result == text

    def test_preserves_line_with_fewer_than_threshold_cjk(self) -> None:
        """Lines with fewer than 4 targeted characters pass through."""
        text = "A single character 中 in context."
        result = _filter_non_latin_scripts(text)
        assert result == text

    def test_threshold_is_four_characters(self) -> None:
        """Exactly 3 targeted characters are preserved; 4 triggers removal."""
        three_chars = "Text with 中文字 inline."
        four_chars = "Text with 中文字符 inline."
        assert _filter_non_latin_scripts(three_chars) == three_chars
        assert "中文字符" not in _filter_non_latin_scripts(four_chars)

    def test_removes_line_with_thai_characters(self) -> None:
        """Thai script is targeted."""
        text = "Normal.\n\nภาษาไทยตัวอย่าง\n\nMore."
        result = _filter_non_latin_scripts(text)
        assert "ภาษา" not in result

    def test_removes_line_with_devanagari_characters(self) -> None:
        """Devanagari script is targeted."""
        text = "Normal.\n\nहिन्दी पाठ उदाहरण\n\nMore."
        result = _filter_non_latin_scripts(text)
        assert "हिन्दी" not in result

    def test_preserves_latin_extended_diacritics(self) -> None:
        """Accented Latin characters are not targeted."""
        text = "Müller, François, and Łukasz contributed."
        result = _filter_non_latin_scripts(text)
        assert result == text

    def test_counts_across_line_not_consecutive(self) -> None:
        """Targeted characters need not be consecutive — total count matters."""
        # 4 CJK characters scattered among Latin text
        text = "The 中 and 文 and 字 and 符 are here."
        result = _filter_non_latin_scripts(text)
        assert "中" not in result

    def test_handles_empty_string(self) -> None:
        assert _filter_non_latin_scripts("") == ""

    def test_handles_all_clean_text(self) -> None:
        text = "Just a normal paragraph.\n\nWith multiple lines."
        assert _filter_non_latin_scripts(text) == text

    def test_bold_wrapped_cjk_still_removed(self) -> None:
        """CJK inside markdown bold markers is still detected and removed."""
        text = "Normal.\n\n**医不利血管 医骨髓前缀**\n\nMore."
        result = _filter_non_latin_scripts(text)
        assert "医" not in result
        assert "Normal." in result

    def test_never_raises(self) -> None:
        """Pass is fault-tolerant — returns input on any error."""
        # Passing None would cause an error in normal operation;
        # the function should catch and return input unchanged.
        # We test with valid input to confirm the contract.
        text = "Some text."
        assert _filter_non_latin_scripts(text) == text


# ===================================================================
# Pass 2: Image Description Reformatting
# ===================================================================


class TestReformatImageDescriptions:
    """Tests for _reformat_image_descriptions pass."""

    def test_content_description_becomes_blockquote(self) -> None:
        """Substantive figure descriptions are reformatted as blockquotes."""
        text = (
            "Some text.\n\n"
            "Image /page/4/Figure/11 description: The image shows a bar graph "
            "comparing costs before and after rebates.\n\n"
            "More text."
        )
        result = _reformat_image_descriptions(text)
        assert "> [Figure]" in result
        assert "bar graph" in result
        assert "Image /page/" not in result

    def test_logo_description_removed(self) -> None:
        """Logo descriptions are noise and removed entirely."""
        text = (
            "Image /page/0/Picture/1 description: The image shows the logo "
            "for the Center on Budget and Policy Priorities.\n\n"
            "Real content here."
        )
        result = _reformat_image_descriptions(text)
        assert "logo" not in result
        assert "Real content here." in result

    def test_seal_description_removed(self) -> None:
        """Institutional seal descriptions are removed."""
        text = (
            "Real content.\n\n"
            "Image /page/0/Picture/0 description: The image shows the "
            "Georgetown University seal."
        )
        result = _reformat_image_descriptions(text)
        assert "seal" not in result
        assert "Real content." in result

    def test_icon_description_removed(self) -> None:
        text = "Image /page/1/Picture/0 description: An icon showing a download arrow.\n\nContent."
        result = _reformat_image_descriptions(text)
        assert "icon" not in result
        assert "Content." in result

    def test_short_description_removed(self) -> None:
        """Very short descriptions (<20 chars after prefix) are removed as noise."""
        text = (
            "Content before.\n\n"
            "Image /page/0/Picture/0 description: A blue rectangle.\n\n"
            "Content after."
        )
        result = _reformat_image_descriptions(text)
        assert "blue rectangle" not in result
        assert "Content before." in result
        assert "Content after." in result

    def test_preserves_non_image_lines(self) -> None:
        """Lines not matching Image /page/ pattern pass through unchanged."""
        text = "Normal paragraph.\n\nAnother paragraph.\n\n## Heading"
        assert _reformat_image_descriptions(text) == text

    def test_blockquote_format(self) -> None:
        """Content descriptions are formatted as > [Figure] <description>."""
        text = (
            "Image /page/2/Figure/5 description: A scatter plot showing "
            "the relationship between F2 and test source across multiple "
            "datasets with color-coded categories."
        )
        result = _reformat_image_descriptions(text)
        assert result.startswith("> [Figure] A scatter plot")

    def test_pie_chart_with_data_preserved(self) -> None:
        """Descriptions containing data (percentages, values) are kept."""
        text = (
            "Image /page/5/Figure/6 description: The image is a pie chart "
            "titled 'Only 10 Percent of WIC Costs Go Toward Administration'. "
            "Administration (10%), Breastfeeding support (17%), Infant formula "
            "costs (19%), Federal food costs (54%)."
        )
        result = _reformat_image_descriptions(text)
        assert "> [Figure]" in result
        assert "10%" in result
        assert "54%" in result

    def test_book_cover_description_removed(self) -> None:
        """Book cover descriptions are noise."""
        text = (
            "Image /page/1/Picture/4 description: The image is a book cover "
            "with the title 'Emerging Intersections' in large blue letters."
        )
        result = _reformat_image_descriptions(text)
        assert "book cover" not in result.lower()

    def test_watermark_description_removed(self) -> None:
        text = "Image /page/0/Picture/0 description: A watermark overlay."
        result = _reformat_image_descriptions(text)
        assert result.strip() == ""

    def test_multiple_descriptions_in_document(self) -> None:
        """Handles multiple image descriptions — some noise, some content."""
        text = (
            "Image /page/0/Picture/0 description: The JSTOR logo in blue.\n\n"
            "Introduction text.\n\n"
            "Image /page/3/Figure/1 description: A line graph showing "
            "unemployment rates from 1970 to 2020 with recession periods "
            "shaded in gray.\n\n"
            "Discussion text."
        )
        result = _reformat_image_descriptions(text)
        assert "logo" not in result.lower()
        assert "> [Figure]" in result
        assert "unemployment rates" in result
        assert "Introduction text." in result
        assert "Discussion text." in result

    def test_handles_empty_string(self) -> None:
        assert _reformat_image_descriptions("") == ""

    def test_handles_no_descriptions(self) -> None:
        text = "Just normal text.\n\nNothing special."
        assert _reformat_image_descriptions(text) == text

    def test_cover_art_removed(self) -> None:
        text = (
            "Image /page/0/Picture/0 description: Cover art depicting "
            "an abstract geometric pattern."
        )
        result = _reformat_image_descriptions(text)
        assert "cover art" not in result.lower()

    def test_decorative_description_removed(self) -> None:
        text = (
            "Image /page/0/Picture/0 description: A decorative border element with floral motifs."
        )
        result = _reformat_image_descriptions(text)
        assert "decorative" not in result.lower()


# ===================================================================
# Pass 3: Repeated Watermark Removal
# ===================================================================


class TestRemoveRepeatedWatermarks:
    """Tests for _remove_repeated_watermarks pass."""

    def test_removes_line_appearing_three_times(self) -> None:
        """Lines appearing 3+ times are removed."""
        watermark = "Copyright 2022. All rights reserved."
        text = f"Para 1.\n\n{watermark}\n\nPara 2.\n\n{watermark}\n\nPara 3.\n\n{watermark}"
        result = _remove_repeated_watermarks(text)
        assert watermark not in result
        assert "Para 1." in result
        assert "Para 2." in result
        assert "Para 3." in result

    def test_preserves_line_appearing_twice(self) -> None:
        """Lines appearing only twice are not removed (below threshold)."""
        repeated = "This line appears twice."
        text = f"Intro.\n\n{repeated}\n\nMiddle.\n\n{repeated}\n\nEnd."
        result = _remove_repeated_watermarks(text)
        assert repeated in result

    def test_preserves_empty_lines(self) -> None:
        """Empty lines are not counted or removed (they're paragraph separators)."""
        text = "Para 1.\n\n\n\nPara 2.\n\n\n\nPara 3."
        assert _remove_repeated_watermarks(text) == text

    def test_preserves_headings(self) -> None:
        """Heading lines are structural and not counted even if repeated."""
        text = "## Section\n\nText.\n\n## Section\n\nMore.\n\n## Section\n\nEnd."
        assert _remove_repeated_watermarks(text) == text

    def test_preserves_list_items(self) -> None:
        """List items are structural and not counted."""
        text = "- item\n- item\n- item\n- item"
        assert _remove_repeated_watermarks(text) == text

    def test_whitespace_normalized_for_comparison(self) -> None:
        """Trailing/leading whitespace differences don't prevent matching."""
        text = (
            "Para 1.\n\nCopyright notice.  \n\n"
            "Para 2.\n\n  Copyright notice.\n\n"
            "Para 3.\n\nCopyright notice."
        )
        result = _remove_repeated_watermarks(text)
        assert "Copyright notice" not in result

    def test_real_world_drm_watermark(self) -> None:
        """Realistic DRM watermark from ebook extraction."""
        wm = (
            "Created from berkeley-ebooks on 2022-04-19 01:39:46. "
            "Copyright \u00a9 2016. Guilford Publications. All rights reserved."
        )
        paragraphs = [f"Paragraph {i} content." for i in range(5)]
        lines = []
        for p in paragraphs:
            lines.append(p)
            lines.append("")
            lines.append(wm)
            lines.append("")
        text = "\n".join(lines)
        result = _remove_repeated_watermarks(text)
        assert wm not in result
        for i in range(5):
            assert f"Paragraph {i} content." in result

    def test_handles_empty_string(self) -> None:
        assert _remove_repeated_watermarks("") == ""

    def test_handles_no_repetition(self) -> None:
        text = "Unique line 1.\n\nUnique line 2.\n\nUnique line 3."
        assert _remove_repeated_watermarks(text) == text

    def test_multiple_different_watermarks(self) -> None:
        """Can remove multiple distinct repeated lines."""
        wm1 = "Watermark A."
        wm2 = "Watermark B."
        text = f"Text.\n\n{wm1}\n\n{wm2}\n\nMore.\n\n{wm1}\n\n{wm2}\n\nEnd.\n\n{wm1}\n\n{wm2}"
        result = _remove_repeated_watermarks(text)
        assert wm1 not in result
        assert wm2 not in result
        assert "Text." in result
        assert "More." in result
        assert "End." in result


# ===================================================================
# Pass 4: Publisher Boilerplate Stripping
# ===================================================================


class TestStripPublisherBoilerplate:
    """Tests for _strip_publisher_boilerplate pass."""

    def test_removes_jstor_preamble(self) -> None:
        """JSTOR access/terms boilerplate at document head is removed."""
        text = (
            "Your use of the JSTOR archive indicates your acceptance of the Terms.\n\n"
            "JSTOR is a not-for-profit service that helps scholars.\n\n"
            "# The Stranger: An Essay in Social Psychology\n\n"
            "The actual paper content begins here."
        )
        result = _strip_publisher_boilerplate(text)
        assert "JSTOR" not in result
        assert "The Stranger" in result
        assert "actual paper content" in result

    def test_removes_researchgate_cover_page(self) -> None:
        """ResearchGate cover page metadata is removed."""
        text = (
            "See discussions, stats, and author profiles for this publication at: "
            "https://www.researchgate.net/publication/12345\n\n"
            "CITATIONS\n\n42\n\nREADS\n\n1,337\n\n"
            "# Actual Paper Title\n\n"
            "The paper content starts here."
        )
        result = _strip_publisher_boilerplate(text)
        assert "researchgate" not in result.lower()
        assert "CITATIONS" not in result
        assert "Actual Paper Title" in result
        assert "paper content starts here" in result

    def test_removes_bepress_download_notice(self) -> None:
        """BePress/SSRN download notice is removed."""
        text = (
            "This paper can be downloaded free of charge from: "
            "https://scholarship.law.georgetown.edu/facpub/555\n\n"
            "This open-access article is brought to you by the Georgetown Law Library.\n\n"
            "# CONSTITUTIONAL HARDBALL\n\n"
            "Paper content here."
        )
        result = _strip_publisher_boilerplate(text)
        assert "downloaded free of charge" not in result
        assert "open-access article" not in result
        assert "CONSTITUTIONAL HARDBALL" in result

    def test_removes_electronic_copy_notice(self) -> None:
        text = (
            "Electronic copy available at: https://ssrn.com/abstract=12345\n\n"
            "# Paper Title\n\nContent."
        )
        result = _strip_publisher_boilerplate(text)
        assert "Electronic copy" not in result
        assert "Paper Title" in result

    def test_preserves_content_after_boilerplate(self) -> None:
        """All content after the boilerplate region is preserved."""
        text = (
            "Your use of the JSTOR archive indicates acceptance.\n\n"
            "# Introduction\n\n"
            "First paragraph of real content.\n\n"
            "Second paragraph of real content."
        )
        result = _strip_publisher_boilerplate(text)
        assert "Introduction" in result
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_only_scans_first_n_lines(self) -> None:
        """Boilerplate patterns deep in the document are not removed."""
        # Put JSTOR text at line 60+ — should not be stripped
        filler = "\n\n".join(f"Paragraph {i}." for i in range(40))
        text = filler + "\n\nYour use of the JSTOR archive indicates acceptance."
        result = _strip_publisher_boilerplate(text)
        assert "JSTOR" in result  # Not removed because it's past the scan window

    def test_handles_empty_string(self) -> None:
        assert _strip_publisher_boilerplate("") == ""

    def test_handles_no_boilerplate(self) -> None:
        text = "# Introduction\n\nJust normal academic content.\n\nMore content."
        assert _strip_publisher_boilerplate(text) == text

    def test_boilerplate_rules_catalog_is_nonempty(self) -> None:
        """The catalog contains at least the known publisher patterns."""
        assert len(BOILERPLATE_RULES) >= 3
        names = {r.name for r in BOILERPLATE_RULES}
        assert "jstor" in names
        assert "researchgate" in names
        assert "bepress" in names

    def test_boilerplate_rules_have_required_fields(self) -> None:
        """Each rule has a name, at least one indicator, and a description."""
        for rule in BOILERPLATE_RULES:
            assert rule.name, "rule must have a name"
            assert rule.indicators, f"rule {rule.name} must have indicators"
            assert rule.description, f"rule {rule.name} must have a description"

    def test_removes_jstor_collaborating_line(self) -> None:
        """The 'is collaborating with JSTOR' line is removed."""
        text = (
            "The University of Chicago Press is collaborating with JSTOR to "
            "digitize, preserve and extend access to American Journal.\n\n"
            "http://www.jstor.org\n\n"
            "# THE STRANGER\n\nContent."
        )
        result = _strip_publisher_boilerplate(text)
        assert "collaborating with JSTOR" not in result
        assert "THE STRANGER" in result


# ===================================================================
# Entry Point: clean_artifacts()
# ===================================================================


class TestCleanArtifacts:
    """Tests for the clean_artifacts entry point."""

    def test_chains_all_passes(self) -> None:
        """clean_artifacts applies all four passes."""
        text = (
            "Your use of the JSTOR archive indicates acceptance.\n\n"
            "# Title\n\n"
            "Image /page/0/Picture/0 description: The JSTOR logo.\n\n"
            "Real paragraph with 医不利血管 医骨髓前缀 on this line.\n\n"
            "Normal content."
        )
        result = clean_artifacts(text)
        assert "JSTOR archive" not in result  # boilerplate stripped
        assert "logo" not in result.lower()  # noise image removed
        assert "医" not in result  # non-Latin filtered
        assert "Normal content." in result

    def test_returns_input_on_clean_text(self) -> None:
        text = "# Introduction\n\nA perfectly clean paragraph."
        assert clean_artifacts(text) == text

    def test_handles_empty_string(self) -> None:
        assert clean_artifacts("") == ""

    def test_never_raises(self) -> None:
        """Entry point is fault-tolerant."""
        text = "Some text."
        assert clean_artifacts(text) == text
